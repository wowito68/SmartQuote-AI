from app.domain.shared.exceptions import DomainError


class CatalogError(DomainError):
    """Base error for catalog extraction and review."""


class CatalogNotFound(CatalogError):
    pass


class CatalogProductNotFound(CatalogError):
    pass


class InvalidProductState(CatalogError):
    pass


class ProductNotApproved(InvalidProductState):
    pass


class InvalidCatalogState(CatalogError):
    pass


class AIExtractionNotFound(CatalogError):
    pass


class AIExtractionFailure(CatalogError):
    pass


class AIResponseValidationError(CatalogError):
    pass


class PromptNotFound(CatalogError):
    pass
