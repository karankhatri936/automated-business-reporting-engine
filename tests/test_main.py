"""Tests for the main orchestrator (fully mocked - no network access).

Verifies the coordination logic in ``main.py``:

- CLI argument parsing
- the happy-path pipeline (API, reports and email mocked at the boundaries)
- API failure handling (propagation after retries are exhausted)
- retry/backoff behavior
- empty API response handling
- invalid source data handling
- email failure must not break the pipeline (reports stay available)
- the ``--no-email`` flag
- scheduled-mode wiring
- process exit codes of the ``main()`` entry point
"""

import unittest
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from automated_business_reporting_engine import main as main_module
from automated_business_reporting_engine.main import (
    EXIT_FAILURE,
    EXIT_SUCCESS,
    main,
    parse_args,
    run_reporting_pipeline,
)
from automated_business_reporting_engine.utils.exceptions import (
    APIError,
    DataProcessingError,
    DataValidationError,
    EmailDeliveryError,
)


def _sample_products():
    """Two valid products shaped exactly like the real API's records."""
    return [
        {
            "id": 1,
            "title": "Alpha Phone",
            "price": 10.0,
            "category": "Electronics",
            "rating": 4.5,
            "stock": 100,
            "discountPercentage": 10.0,
            "brand": "BrandA",
            "availabilityStatus": "In Stock",
        },
        {
            "id": 2,
            "title": "Beta Notebook",
            "price": 5.0,
            "category": "Books",
            "rating": 4.0,
            "stock": 8,
            "discountPercentage": 5.0,
            "brand": "BrandB",
            "availabilityStatus": "Low Stock",
        },
    ]


class TestParseArgs(unittest.TestCase):
    """CLI flag parsing."""

    def test_defaults(self):
        args = parse_args([])
        self.assertFalse(args.schedule)
        self.assertFalse(args.no_email)

    def test_schedule_and_no_email_flags(self):
        args = parse_args(["--schedule", "--no-email"])
        self.assertTrue(args.schedule)
        self.assertTrue(args.no_email)


class TestRunReportingPipeline(unittest.TestCase):
    """Pipeline coordination with the network boundary mocked out.

    Validation, processing and KPI calculation run for real; only the API
    client, the report generators and email delivery are mocked.
    """

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.excel_path = Path(self.tmp.name) / "Business_Report.xlsx"
        self.pdf_path = Path(self.tmp.name) / "Business_Report.pdf"

    def _mock_pipeline(self, stack, products=None, email_side_effect=None):
        """Patch APIClient, both report generators and email delivery.

        ``send_report_email`` is ALWAYS mocked so tests cannot send a real
        message even if a developer's .env enables email.
        """
        client = MagicMock()
        client.return_value.get_all_products.return_value = (
            _sample_products() if products is None else products
        )
        stack.enter_context(patch.object(main_module, "APIClient", client))
        stack.enter_context(
            patch.object(
                main_module,
                "generate_excel_report",
                return_value=self.excel_path,
            )
        )
        stack.enter_context(
            patch.object(
                main_module,
                "generate_pdf_report",
                return_value=self.pdf_path,
            )
        )
        email_mock = stack.enter_context(
            patch.object(
                main_module,
                "send_report_email",
                return_value=False,
                side_effect=email_side_effect,
            )
        )
        return client, email_mock

    def test_pipeline_success(self):
        with ExitStack() as stack:
            client, email_mock = self._mock_pipeline(stack)
            result = run_reporting_pipeline()
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["products_count"], 2)
        self.assertEqual(result["excel_path"], self.excel_path)
        self.assertEqual(result["pdf_path"], self.pdf_path)
        self.assertEqual(result["email_status"], "skipped")
        client.return_value.get_all_products.assert_called_once()
        email_mock.assert_called_once()

    def test_api_failure_propagates_after_retries(self):
        """A persistent API failure raises APIError after all retry attempts."""
        with ExitStack() as stack:
            client, _ = self._mock_pipeline(stack)
            client.return_value.get_all_products.side_effect = APIError(
                "connection refused"
            )
            time_mock = MagicMock()
            stack.enter_context(patch.object(main_module, "time", time_mock))
            with self.assertRaises(APIError):
                run_reporting_pipeline()
            self.assertEqual(
                client.return_value.get_all_products.call_count,
                main_module.API_RETRY_ATTEMPTS,
            )
            self.assertEqual(
                time_mock.sleep.call_count,
                main_module.API_RETRY_ATTEMPTS - 1,
            )

    def test_retry_recovers_from_transient_failure(self):
        """A transient API failure is retried and the run succeeds."""
        with ExitStack() as stack:
            client, _ = self._mock_pipeline(stack)
            client.return_value.get_all_products.side_effect = [
                APIError("timeout"),
                _sample_products(),
            ]
            stack.enter_context(patch.object(main_module, "time"))
            result = run_reporting_pipeline()
        self.assertEqual(result["status"], "success")
        self.assertEqual(client.return_value.get_all_products.call_count, 2)

    def test_empty_api_response_raises(self):
        """An empty API response fails cleanly instead of reporting nothing."""
        with ExitStack() as stack:
            self._mock_pipeline(stack, products=[])
            with self.assertRaises(DataProcessingError):
                run_reporting_pipeline()

    def test_invalid_source_data_fails_pipeline(self):
        """A record failing validation terminates the run cleanly."""
        bad_products = _sample_products()
        bad_products[0]["price"] = -5.0
        with ExitStack() as stack:
            self._mock_pipeline(stack, products=bad_products)
            with self.assertRaises(DataValidationError):
                run_reporting_pipeline()

    def test_email_failure_does_not_break_pipeline(self):
        """SMTP failure is reported as 'failed' while the run still succeeds."""
        with ExitStack() as stack:
            _, email_mock = self._mock_pipeline(
                stack, email_side_effect=EmailDeliveryError("SMTP down")
            )
            result = run_reporting_pipeline()
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["email_status"], "failed")
        email_mock.assert_called_once()

    def test_no_email_flag_skips_delivery(self):
        """--no-email prevents any email delivery attempt."""
        with ExitStack() as stack:
            _, email_mock = self._mock_pipeline(stack)
            result = run_reporting_pipeline(no_email=True)
        email_mock.assert_not_called()
        self.assertEqual(result["email_status"], "disabled_by_flag")



class TestMainEntryPoint(unittest.TestCase):
    """Exit-code behavior of the ``main()`` entry point."""

    @staticmethod
    def _result():
        return {
            "status": "success",
            "products_count": 2,
            "excel_path": "Business_Report.xlsx",
            "pdf_path": "Business_Report.pdf",
            "email_status": "skipped",
        }

    def test_success_returns_zero(self):
        with patch.object(
            main_module, "run_reporting_pipeline", return_value=self._result()
        ):
            self.assertEqual(main([]), EXIT_SUCCESS)

    def test_known_failure_returns_exit_failure(self):
        with patch.object(
            main_module, "run_reporting_pipeline", side_effect=APIError("down")
        ):
            self.assertEqual(main([]), EXIT_FAILURE)

    def test_unexpected_exception_returns_exit_failure(self):
        """Unexpected exceptions are logged and still exit cleanly."""
        with patch.object(
            main_module,
            "run_reporting_pipeline",
            side_effect=RuntimeError("surprise"),
        ):
            self.assertEqual(main([]), EXIT_FAILURE)

    def test_skipped_run_returns_exit_failure(self):
        """A run skipped due to an in-progress run exits with failure."""
        with patch.object(
            main_module, "run_reporting_pipeline"
        ) as mock_pipeline, patch.object(main_module, "run_job_once", False):
            self.assertEqual(main([]), EXIT_FAILURE)
        mock_pipeline.assert_not_called()

    def test_schedule_mode_starts_scheduler_once(self):
        """--schedule registers exactly one job and waits on the scheduler."""
        with patch.object(main_module, "ReportScheduler") as scheduler_cls:
            instance = scheduler_cls.return_value
            instance.start.return_value = True
            instance.wait.return_value = None
            instance.next_run_time = "2026-09-11 12:00:00+00:00"
            code = main(["--schedule", "--no-email"])
        self.assertEqual(code, EXIT_SUCCESS)
        instance.start.assert_called_once()


if __name__ == "__main__":
    unittest.main()


