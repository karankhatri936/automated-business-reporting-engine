# Automated Business Reporting Engine

A Python application that retrieves product catalog data from a business API,
validates and processes it, computes KPIs, and delivers professional
**Excel** and **PDF executive reports**, with optional **email delivery** and
**scheduled execution**.

The initial data source is the public **DummyJSON Products API**
(`https://dummyjson.com/products`). The data describes a **product catalog /
inventory snapshot** — prices, stock levels, ratings, discounts, categories —
retrieved live from the API. **All figures in the reports are computed from
that actual data; nothing is fabricated.**

## 1. What the project does

On each run the engine executes this pipeline:

```
API (DummyJSON products)
  → Data retrieval (paginated, retried on transient failures)
  → Validation (schema, types, ranges)
  → Cleaning & transformation (Pandas, derived fields)
  → KPI calculation (single source of truth)
  → Excel report  (output/excel/Business_Report_YYYY-MM-DD.xlsx)
  → PDF executive report (output/pdf/Business_Report_YYYY-MM-DD.pdf)
  → Email delivery (optional, both reports attached)
  → Scheduling (optional, fixed interval)
```

Everything is logged to `logs/application.log` and the console, and the
process exits with a meaningful exit code (`0` success, `1` failure,
`130` interrupted).

## 2. Architecture

The application is a pipeline of **independent, reusable modules**. `main.py`
only orchestrates — each step lives in its own package:

| Stage | Module | Responsibility |
|---|---|---|
| Configuration | `config.py` | Dataclasses reading environment variables |
| API retrieval | `api/client.py` | Paginated `GET` requests, error mapping to domain exceptions |
| Validation | `data/validator.py` | Reject malformed records (kept separate from transformation) |
| Processing | `data/processor.py` | Clean records, derive fields, build the DataFrame |
| KPIs | `analytics/kpis.py` | `KPIEngine` — all metrics, used by BOTH reports |
| Excel report | `reports/excel_report.py` | OpenPyXL workbook (5 sheets, charts) |
| PDF report | `reports/pdf_report.py` | ReportLab executive summary |
| Email | `mail/sender.py` | SMTP transport with attachments (optional) |
| Scheduling | `scheduler/scheduler.py` | APScheduler interval job with overlap protection |
| Logging | `utils/logger.py` | File + console logging |
| Exceptions | `utils/exceptions.py` | Domain exception hierarchy |

Key design decisions:

- **The KPI engine is the single source of truth.** The Excel and PDF
  generators only format the output of `KPIEngine.calculate_all()`, so the
  two reports can never contradict each other.
- **Swappable data source.** The API URL, timeout and pagination limit are
  configuration. The client only assumes a JSON response shaped like
  `{"products": [...], "total": n}` (or a bare list) and returns plain Python
  dicts, so replacing DummyJSON with another business API is a
  configuration + small adapter change, not a rewrite.
- **Validation is separate from transformation.** `validator.py` rejects bad
  records; `processor.py` normalizes good ones.
- **Email never blocks the pipeline.** A delivery failure is logged and the
  generated reports remain on disk.
- The email package is named `mail/` (not `email/`) to avoid shadowing
  Python's standard-library `email` package.
- The project root contains an `__init__.py`, making the folder importable as
  the `automated_business_reporting_engine` package; run commands from the
  project directory.

## 3. Project structure

```
automated_business_reporting_engine/
│
├── main.py                  # Orchestrator (pipeline + CLI)
├── config.py                # Environment-driven configuration
├── requirements.txt
├── README.md
├── .env.example             # Example configuration (no real credentials)
├── .gitignore
│
├── api/
│   └── client.py            # Paginated API client
├── data/
│   ├── validator.py         # Record validation
│   └── processor.py         # Cleaning, derived fields, DataFrame
├── analytics/
│   └── kpis.py              # KPIEngine (metrics + grouped analysis)
├── reports/
│   ├── excel_report.py      # Excel workbook generator
│   └── pdf_report.py        # PDF executive summary generator
├── mail/
│   └── sender.py            # SMTP delivery (optional)
├── scheduler/
│   └── scheduler.py         # APScheduler wrapper (single-job guarantee)
├── utils/
│   ├── logger.py            # Logging setup
│   └── exceptions.py        # Exception hierarchy
│
├── tests/                   # pytest suite (mocked API/SMTP)
├── output/
│   ├── excel/               # Generated .xlsx reports (git-ignored)
│   └── pdf/                 # Generated .pdf reports (git-ignored)
└── logs/                    # application.log (git-ignored)
```


## 4. Installation

Requirements: **Python 3.10+** (developed and tested on 3.14).

```bash
cd automated_business_reporting_engine

# Create and activate a virtual environment (recommended)
python -m venv .venv
.venv\Scripts\activate        # Windows (PowerShell)
# source .venv/bin/activate   # Linux/macOS

# Install dependencies
pip install -r requirements.txt

# Create your local configuration
copy .env.example .env        # Windows
# cp .env.example .env        # Linux/macOS
```

The application runs without a `.env` file (sensible defaults, email
disabled), but creating one is recommended.

## 5. Dependencies

| Package | Used for |
|---|---|
| `requests` | HTTP client for the API |
| `pandas` | Validation output → cleaning → DataFrame → KPIs |
| `openpyxl` | Excel workbook generation |
| `reportlab` | PDF report generation |
| `apscheduler` | Interval-based scheduling |
| `python-dotenv` | Loads `.env` (optional at runtime — the app works without it) |
| `pytest` | Test suite |

## 6. Environment variables

All settings are read by `config.py` from environment variables (typically
via `.env`). Defaults shown in parentheses.

| Variable | Default | Purpose |
|---|---|---|
| `API_URL` | `https://dummyjson.com/products` | Data source endpoint |
| `API_TIMEOUT` | `30` | HTTP timeout in seconds |
| `API_PAGINATION_LIMIT` | `100` | Records fetched per page |
| `OUTPUT_DIR` | `output` | Base output directory |
| `EXCEL_DIR` | `excel` | Excel subdirectory (under `OUTPUT_DIR`) |
| `PDF_DIR` | `pdf` | PDF subdirectory (under `OUTPUT_DIR`) |
| `REPORT_NAME` | `Business_Report` | Report file prefix |
| `EMAIL_ENABLED` | `false` | Opt-in switch for email delivery |
| `SMTP_HOST` | `smtp.gmail.com` | SMTP server |
| `SMTP_PORT` | `587` | SMTP port (587 STARTTLS, 465 implicit SSL) |
| `EMAIL_SENDER` | *(empty)* | Sender address |
| `EMAIL_RECIPIENT` | *(empty)* | Recipient address |
| `EMAIL_PASSWORD` | *(empty)* | SMTP password / app password — **env only, never committed** |
| `SCHEDULER_INTERVAL_MINUTES` | `60` | Interval between scheduled runs |

Example `.env` (no real credentials — see `.env.example`):

```env
API_URL=https://dummyjson.com/products
API_TIMEOUT=30
API_PAGINATION_LIMIT=100
REPORT_NAME=Business_Report
EMAIL_ENABLED=false
SCHEDULER_INTERVAL_MINUTES=60
```

## 7. How to run manually

From the project directory:

```bash
python main.py               # single run: fetch → validate → process → KPIs → Excel + PDF → email (if enabled)
python main.py --no-email    # single run, email skipped even if enabled
```

A successful run logs a summary line and returns exit code `0`. API retrieval
is retried up to 3 times with a short backoff before the run terminates
cleanly. The reports are written to:

- `output/excel/Business_Report_YYYY-MM-DD.xlsx`
- `output/pdf/Business_Report_YYYY-MM-DD.pdf`

## 8. How to run scheduled mode

```bash
python main.py --schedule
```

The process stays in the foreground, runs the reporting job immediately and
then every `SCHEDULER_INTERVAL_MINUTES` minutes (default 60), and stops
gracefully on `Ctrl+C`. To change the interval:

```env
SCHEDULER_INTERVAL_MINUTES=30
```

Overlap protection: a process-wide lock guarantees **only one reporting run
at a time**. Manual and scheduled runs share the same lock; a trigger that
arrives while a run is active is logged and skipped (never queued), and
APScheduler itself is configured with `max_instances=1` and `coalesce=True`
so duplicate jobs can never accumulate.

## 9. How email configuration works

Email is **optional** and disabled by default. To enable it:

```env
EMAIL_ENABLED=true
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
EMAIL_SENDER=you@example.com
EMAIL_RECIPIENT=recipient@example.com
EMAIL_PASSWORD=your-app-password
```

Notes:

- Use an **app password** (e.g. Gmail requires one for SMTP), not your
  account password. The value is read only from the environment — it is
  never hard-coded and never logged.
- Port `587` uses STARTTLS; port `465` uses implicit SSL.
- The email contains a concise body with a few headline figures taken from
  the same KPI results as the reports, plus both reports as attachments.
- Behavior on failure: the error is logged and the pipeline continues — the
  generated Excel/PDF files are **never** deleted. `--no-email` skips
  delivery entirely.

## 10. Where reports are generated

| Report | Path | Contents |
|---|---|---|
| Excel | `output/excel/Business_Report_YYYY-MM-DD.xlsx` | 5 sheets: **Dashboard** (KPI summary, inventory status, top products, pie + bar charts), **Product Data** (full processed dataset as an Excel table), **Category Analysis**, **Product Analysis** (rankings), **Report Metadata** (API source, timestamp, record count, version) |
| PDF | `output/pdf/Business_Report_YYYY-MM-DD.pdf` | Executive summary: KPI table, category highlights, top products, data-derived observations, metadata |

Both reports share the same metadata and the same KPI results. `logs/` holds
the application log; `output/` and `logs/` are git-ignored.

## 11. Testing

```bash
python -m pytest tests -v
```

The suite (8 test modules) covers the API client (mocked responses,
pagination, duplicate/stall detection), validation, processing, KPI math,
Excel and PDF generation (workbook/PDF actually produced and inspected),
email (mocked SMTP), the scheduler, and the `main.py` orchestrator.
**Tests do not depend on the real API or a real SMTP server** — network
boundaries are mocked.

## 12. Future extensions

The architecture was designed for these, none of which require a rewrite:

- **Different business API** — point `API_URL` at the new endpoint and adapt
  `api/client.py` to the response shape; validation/processing/KPIs follow.
- **More report formats** — CSV/HTML generators can consume the same
  DataFrame + KPI dict.
- **Persistence** — load reports or processed data into a database.
- **Deeper scheduling** — cron-style triggers via APScheduler, or system
  schedulers (Task Scheduler/cron) invoking `python main.py` directly.
- **Delivery options** — Slack/webhook notifications alongside email.

## Known limitations

- DummyJSON is demo catalog data; the KPIs describe that catalog (inventory
  and pricing), not real sales or financial performance.
- Email delivery is unit-tested with a mocked SMTP server only; verify
  settings with your real provider before relying on it.
- The scheduler is a single background process; it is not a distributed or
  clustered scheduler.
- Stock-status thresholds (low / medium / high) are fixed heuristics in
  `data/processor.py`, not configurable policy.

