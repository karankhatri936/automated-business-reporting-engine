"""Main orchestrator for the Automated Business Reporting Engine.

Coordinates the complete reporting pipeline and delegates the actual work to
dedicated, reusable modules:

    API retrieval  -> api.client.APIClient
    Validation     -> data.validator.validate_product_data
    Processing     -> data.processor (clean, derived fields, DataFrame)
    Business KPIs  -> analytics.kpis.KPIEngine
    Excel report   -> reports.excel_report.generate_excel_report
    PDF report     -> reports.pdf_report.generate_pdf_report
    Email delivery -> mail.sender.send_report_email
    Scheduling     -> scheduler.scheduler.run_job_once / ReportScheduler

Usage:
    python main.py                 # single manual run
    python main.py --schedule      # run on a schedule (see config)
    python main.py --no-email      # skip email even if enabled in config

Failure handling:
    - API failures are retried a few times, then terminate cleanly.
    - Report generation failures are logged with useful context and exit 1.
    - Email failures are logged but NEVER delete generated reports or abort
      the pipeline.
    - Unexpected exceptions are logged with a traceback and exit 1 -- they
      are never silently swallowed.
"""

from __future__ import annotations

import argparse
import functools
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# ── Environment bootstrap ───────────────────────────────────────────────
# Load .env BEFORE configuration is imported: config.py reads environment
# variables at import time.
# Add both the project root and its parent to sys.path so the package can be
# imported consistently regardless of how main.py is launched (this matters
# because the submodules use relative imports such as ``..config``).
PROJECT_ROOT = Path(__file__).resolve().parent
for entry in (str(PROJECT_ROOT), str(PROJECT_ROOT.parent)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:  # python-dotenv is optional at runtime
    pass
# Configuration and package modules (imported AFTER .env is loaded).
from automated_business_reporting_engine.analytics.kpis import KPIEngine
from automated_business_reporting_engine.api.client import APIClient
from automated_business_reporting_engine.config import REPORT_VERSION, config
from automated_business_reporting_engine.data.processor import (
    add_derived_fields,
    clean_product_data,
    create_dataframe,
)
from automated_business_reporting_engine.data.validator import validate_product_data
from automated_business_reporting_engine.mail.sender import send_report_email
from automated_business_reporting_engine.reports.excel_report import generate_excel_report
from automated_business_reporting_engine.reports.pdf_report import generate_pdf_report
from automated_business_reporting_engine.scheduler.scheduler import (
    ReportScheduler,
    run_job_once,
)
from automated_business_reporting_engine.utils.exceptions import (
    APIError,
    DataProcessingError,
    EmailDeliveryError,
    ReportingEngineError,
)
from automated_business_reporting_engine.utils.logger import setup_logger

logger = setup_logger("main")

#: How many times to try the initial API retrieval before giving up.
API_RETRY_ATTEMPTS = 3
#: Seconds to wait between retries.
API_RETRY_BACKOFF_SECONDS = 2.0

# Exit codes returned to the operating system.
EXIT_SUCCESS = 0
EXIT_FAILURE = 1
EXIT_INTERRUPTED = 130


def _fetch_products_with_retry(client: APIClient) -> List[Dict[str, Any]]:
    """Fetch all products via the API client with a small retry loop.

    Retrying a GET request is safe and gives transient network failures a
    chance to recover. Once the attempts are exhausted the last error is
    re-raised so the caller can terminate cleanly.

    Raises:
        APIError: After all retry attempts have been exhausted.
    """
    last_error: Optional[Exception] = None
    for attempt in range(1, API_RETRY_ATTEMPTS + 1):
        try:
            return client.get_all_products()
        except APIError as exc:
            last_error = exc
            if attempt < API_RETRY_ATTEMPTS:
                logger.warning(
                    "API fetch attempt %s/%s failed (%s). Retrying in %ss.",
                    attempt,
                    API_RETRY_ATTEMPTS,
                    exc,
                    API_RETRY_BACKOFF_SECONDS,
                )
                time.sleep(API_RETRY_BACKOFF_SECONDS)
    assert last_error is not None
    raise last_error


def _build_metadata(record_count: int) -> Dict[str, Any]:
    """Shared metadata used by BOTH reports so they stay consistent."""
    return {
        "report_title": config.output.report_name,
        "report_version": REPORT_VERSION,
        "api_source": config.api.url,
        "generation_timestamp": f"{datetime.now():%Y-%m-%d %H:%M:%S}",
        "record_count": record_count,
    }


def _build_email_summary(
    kpis: Dict[str, Any], excel_path: Path, pdf_path: Path
) -> Dict[str, Any]:
    """Subset of the KPI results rendered in the email body."""
    general = kpis["general"]
    return {
        "report_date": f"{datetime.now():%Y-%m-%d}",
        "total_products": general["total_products"],
        "total_inventory_value": general["total_inventory_value"],
        "average_price": general["average_price"],
        "average_rating": general["average_rating"],
        "low_stock_count": general["low_stock_count"],
        "excel_filename": excel_path.name,
        "pdf_filename": pdf_path.name,
    }


def _send_email(
    excel_path: Path,
    pdf_path: Path,
    kpis: Dict[str, Any],
    no_email: bool,
) -> str:
    """Deliver the reports by email without jeopardizing the pipeline.

    Returns one of: "sent", "skipped", "disabled_by_flag", "failed".
    Failures are logged so the reports are preserved.
    """
    if no_email:
        logger.info("Email delivery disabled by --no-email flag")
        return "disabled_by_flag"

    summary = _build_email_summary(kpis, excel_path, pdf_path)
    try:
        sent = send_report_email(excel_path, pdf_path, summary=summary)
        if sent:
            logger.info("Report email sent to %s", config.email.recipient)
            return "sent"
        logger.info(
            "Email delivery skipped (EMAIL_ENABLED=%s or SMTP configuration "
            "incomplete); reports preserved on disk",
            config.email.enabled,
        )
        return "skipped"
    except EmailDeliveryError as exc:
        logger.error(
            "Email delivery failed (%s). Generated reports remain available "
            "at %s and %s",
            exc,
            excel_path,
            pdf_path,
        )
        return "failed"


def run_reporting_pipeline(no_email: bool = False) -> Dict[str, Any]:
    """Execute the complete reporting pipeline once.

    Args:
        no_email: When True, skip email delivery even if it is configured.

    Returns:
        A summary dict with paths to the generated reports and the email
        outcome.

    Raises:
        APIError: After API retries are exhausted.
        DataValidationError / DataProcessingError: Bad or empty source data.
        ExcelReportError / PDFReportError: Report generation failures.
    """
    logger.info("Reporting pipeline started")

    # 1. API retrieval (with retry).
    client = APIClient()
    products = _fetch_products_with_retry(client)
    logger.info("Retrieved %s product records from API", len(products))

    if not products:
        raise DataProcessingError(
            "No product records were retrieved from the API; "
            "there is nothing to validate or report on."
        )

    # 2. Validation (kept separate from transformation).
    validate_product_data(products)
    logger.info("Validation passed for %s records", len(products))

    # 3. Data cleaning and derived fields -> DataFrame.
    cleaned = clean_product_data(products)
    derived = add_derived_fields(cleaned)
    df = create_dataframe(derived)
    logger.info("Processed dataset into DataFrame (%s rows)", len(df))

    # 4. KPI calculation (single source of truth for both reports).
    kpis = KPIEngine(df).calculate_all()
    logger.info("KPI calculation complete")

    # 5. + 6. Reports (both built from the SAME KPI results).
    metadata = _build_metadata(int(df["id"].nunique()))
    excel_path = generate_excel_report(df, kpis, metadata=metadata)
    pdf_path = generate_pdf_report(df, kpis, metadata=metadata)
    logger.info("Reports generated: %s | %s", excel_path, pdf_path)

    # 7. Email (optional and never destructive).
    email_status = _send_email(excel_path, pdf_path, kpis, no_email)

    logger.info("Reporting pipeline completed successfully")
    return {
        "status": "success",
        "products_count": int(df["id"].nunique()),
        "excel_path": excel_path,
        "pdf_path": pdf_path,
        "email_status": email_status,
    }


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        prog="main.py",
        description=(
            "Automated Business Reporting Engine - fetch catalog data from an "
            "API, validate and process it, and generate Excel + PDF reports."
        ),
    )
    parser.add_argument(
        "--schedule",
        action="store_true",
        help=(
            "Run continuously on a schedule instead of a single run. The "
            "interval is read from SCHEDULER_INTERVAL_MINUTES (default 60)."
        ),
    )
    parser.add_argument(
        "--no-email",
        action="store_true",
        help="Skip email delivery even when email is enabled in the config.",
    )
    return parser.parse_args(argv)


def _run_scheduled(job: Callable[[], Any]) -> int:
    """Start the background scheduler and block until interrupted."""
    scheduler = ReportScheduler()
    started = scheduler.start(job)
    if not started:
        logger.error(
            "Could not start the scheduler (it may already be running)."
        )
        return EXIT_FAILURE
    logger.info(
        "Scheduled execution active - reporting job every %s minute(s), "
        "next run at %s. Press Ctrl+C to stop.",
        config.scheduler.interval_minutes,
        scheduler.next_run_time,
    )
    scheduler.wait()  # Handles KeyboardInterrupt with a graceful shutdown.
    return EXIT_SUCCESS


def main(argv: Optional[List[str]] = None) -> int:
    """Application entry point; returns a process exit code."""
    args = parse_args(argv)
    job = functools.partial(run_reporting_pipeline, no_email=args.no_email)

    try:
        if args.schedule:
            return _run_scheduled(job)

        result = run_job_once(job)
        if result is False:
            logger.warning(
                "A reporting run was already in progress; this run was skipped."
            )
            return EXIT_FAILURE
        if result is None:
            return EXIT_FAILURE

        logger.info(
            "Run summary: %s products | Excel: %s | PDF: %s | Email: %s",
            result["products_count"],
            result["excel_path"],
            result["pdf_path"],
            result["email_status"],
        )
        return EXIT_SUCCESS

    except KeyboardInterrupt:
        logger.info("Interrupted; exiting cleanly")
        return EXIT_INTERRUPTED
    except ReportingEngineError as exc:
        # Known failure: log the useful message and terminate cleanly.
        logger.error("Pipeline failed: %s", exc)
        return EXIT_FAILURE
    except Exception as exc:  # noqa: BLE001 - never silently swallow surprises
        logger.exception("Unexpected pipeline failure: %s", exc)
        return EXIT_FAILURE


if __name__ == "__main__":
    sys.exit(main())