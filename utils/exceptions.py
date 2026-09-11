"""Custom exception classes for the reporting engine."""


class ReportingEngineError(Exception):
    """Base exception for the reporting engine."""


class APIClientError(ReportingEngineError):
    """Raised when API client encounters an error."""


class APITimeoutError(ReportingEngineError):
    """Raised when an API request times out."""


class APIResponseError(ReportingEngineError):
    """Raised when API returns an unexpected response."""


class APIPaginationError(ReportingEngineError):
    """Raised when pagination fails or data is inconsistent."""


# Alias for backward compatibility
APIError = APIClientError


class DataValidationError(ReportingEngineError):
    """Raised when data validation fails."""


class DataProcessingError(ReportingEngineError):
    """Raised when data processing fails."""


class ReportGenerationError(ReportingEngineError):
    """Raised when report generation fails."""


class ExcelReportError(ReportingEngineError):
    """Raised when Excel report generation fails."""


class PDFReportError(ReportingEngineError):
    """Raised when PDF report generation fails."""


class EmailDeliveryError(ReportingEngineError):
    """Raised when email delivery fails."""


class SchedulerError(ReportingEngineError):
    """Raised when scheduler operations fail."""