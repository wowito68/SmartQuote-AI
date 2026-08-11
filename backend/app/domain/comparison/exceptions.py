from app.domain.shared.exceptions import DomainError


class ComparisonError(DomainError):
    """Base exception for deterministic quote comparison failures."""


class ComparisonNotReady(ComparisonError):
    pass


class ComparisonNotFound(ComparisonError):
    pass
