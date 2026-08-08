class ApplicationError(Exception):
    """Base exception for application orchestration errors."""


class ResourceNotFound(ApplicationError):
    """Requested application resource does not exist."""


class OperationConflict(ApplicationError):
    """Operation conflicts with the current persisted workflow state."""


class StorageError(ApplicationError):
    """Private storage operation failed."""


class AIProviderError(ApplicationError):
    """Configured AI provider could not complete the requested operation."""


class EmailProviderError(ApplicationError):
    """Configured email provider could not complete the requested operation."""


class TenderNotFound(ResourceNotFound):
    """Raised when a tender cannot be found."""


class TenderCreatorNotFound(ApplicationError):
    """Raised when the requested creator does not exist."""
