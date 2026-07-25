from app.domain.shared.exceptions import DomainError


class TenderError(DomainError):
    """Base exception for tender business rules."""


class InvalidTenderState(TenderError):
    """Raised when a tender status transition is not allowed."""


class TenderAlreadyArchived(TenderError):
    """Raised when an archived tender receives a write operation."""


class InvalidDeadline(TenderError):
    """Raised when a tender deadline violates chronological rules."""
