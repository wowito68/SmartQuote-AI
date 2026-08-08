from app.domain.shared.exceptions import DomainError


class QuoteError(DomainError):
    """Base exception for quote workflow failures."""


class QuoteNotFound(QuoteError):
    pass


class DuplicateQuote(QuoteError):
    pass


class InvalidQuoteState(QuoteError):
    pass


class QuoteExtractionFailure(QuoteError):
    pass


class QuoteProviderError(QuoteExtractionFailure):
    pass


class QuoteStorageError(QuoteError):
    pass


class ComparisonNotReady(QuoteError):
    pass


class ComparisonNotFound(QuoteError):
    pass
