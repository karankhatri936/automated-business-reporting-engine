"""Configuration for the Automated Business Reporting Engine."""

import os
from dataclasses import dataclass, field
from pathlib import Path

# Shared value so Excel and PDF reports stay version-consistent.
REPORT_VERSION = "1.0"

# Project root. Relative output paths are anchored here so the engine writes
# to the expected directories no matter which working directory it runs in.
PROJECT_ROOT = Path(__file__).resolve().parent


def _resolve_path(value: str) -> Path:
    """Return *value* as an absolute path (relative paths anchor to PROJECT_ROOT)."""
    path = Path(os.path.expanduser(str(value)))
    return path if path.is_absolute() else PROJECT_ROOT / path



@dataclass
class APIConfig:
    """API connection settings."""

    url: str = os.getenv("API_URL", "https://dummyjson.com/products")
    timeout: int = int(os.getenv("API_TIMEOUT", "30"))


@dataclass
class PaginationConfig:
    """Pagination settings."""

    limit: int = int(os.getenv("API_PAGINATION_LIMIT", "100"))


@dataclass
class OutputConfig:
    """Output directory settings.

    Relative directory values are anchored to the project root instead of the
    current working directory; absolute values (e.g. from tests) are kept.
    """

    base_dir: Path = field(
        default_factory=lambda: _resolve_path(os.getenv("OUTPUT_DIR", "output"))
    )
    excel_dir: Path = field(
        default_factory=lambda: Path(os.getenv("EXCEL_DIR", "excel"))
    )
    pdf_dir: Path = field(
        default_factory=lambda: Path(os.getenv("PDF_DIR", "pdf"))
    )
    report_name: str = os.getenv("REPORT_NAME", "Business_Report")

    def __post_init__(self):
        self.base_dir = _resolve_path(self.base_dir)
        # Relative excel/pdf subdirectories hang off base_dir.
        if not self.excel_dir.is_absolute():
            self.excel_dir = self.base_dir / self.excel_dir
        if not self.pdf_dir.is_absolute():
            self.pdf_dir = self.base_dir / self.pdf_dir



@dataclass
class EmailConfig:
    """SMTP email settings."""

    enabled: bool = os.getenv("EMAIL_ENABLED", "false").lower() == "true"
    smtp_host: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    sender: str = os.getenv("EMAIL_SENDER", "")
    recipient: str = os.getenv("EMAIL_RECIPIENT", "")
    password: str = os.getenv("EMAIL_PASSWORD", "")


@dataclass
class SchedulerConfig:
    """Scheduler settings."""

    interval_minutes: int = int(os.getenv("SCHEDULER_INTERVAL_MINUTES", "60"))


@dataclass
class Config:
    """Application configuration."""

    api: APIConfig = field(default_factory=APIConfig)
    pagination: PaginationConfig = field(default_factory=PaginationConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    email: EmailConfig = field(default_factory=EmailConfig)
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)


config = Config()