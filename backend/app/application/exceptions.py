class ApplicationError(Exception):
    """Base exception for application orchestration errors."""


class TenderNotFound(ApplicationError):
    """Raised when a tender cannot be found."""


class TenderCreatorNotFound(ApplicationError):
    """Raised when the requested creator does not exist."""
