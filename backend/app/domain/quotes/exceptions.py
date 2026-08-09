from app.domain.shared.exceptions import DomainError


class QuoteError(DomainError):
    """Base exception for quote workflow failures."""


class QuoteNotFound(QuoteError):
    pass


class QuoteDocumentNotFound(QuoteError):
    pass


class QuoteItemNotFound(QuoteError):
    pass


class DuplicateQuote(QuoteError):
    pass


class InvalidQuoteState(QuoteError):
    pass


class QuoteExtractionFailure(QuoteError):
    pass


class RetryableQuoteExtractionFailure(QuoteExtractionFailure):
    pass


class QuoteProviderError(RetryableQuoteExtractionFailure):
    pass


class QuoteStorageError(RetryableQuoteExtractionFailure):
    pass


class ComparisonNotReady(QuoteError):
    pass


class ComparisonNotFound(QuoteError):
    pass
