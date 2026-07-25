class DomainError(Exception):
    """Base exception for domain rule violations."""


class ValidationError(DomainError):
    """Raised when a domain value is invalid."""


class InvalidStateTransitionError(DomainError):
    """Raised when a domain entity receives an invalid state transition."""

