"""Custom exception classes for the reporting engine."""


class ReportingEngineError(Exception):
    """Base exception for the reporting engine."""


class APIError(ReportingEngineError):
    """Raised when API client encounters an error."""


class APIPaginationError(ReportingEngineError):
    """Raised when pagination fails or data is inconsistent."""


class DataValidationError(ReportingEngineError):
    """Raised when data validation fails."""


class DataProcessingError(ReportingEngineError):
    """Raised when data processing fails."""


class ExcelReportError(ReportingEngineError):
    """Raised when Excel report generation fails."""


class PDFReportError(ReportingEngineError):
    """Raised when PDF report generation fails."""


class EmailDeliveryError(ReportingEngineError):
    """Raised when email delivery fails."""


class SchedulerError(ReportingEngineError):
    """Raised when scheduler operations fail."""