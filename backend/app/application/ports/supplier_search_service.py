from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID


@dataclass(frozen=True, slots=True)
class SupplierSearchProduct:
    product_id: UUID
    name: str
    description: str | None
    category: str | None
    specifications: dict[str, str]


@dataclass(frozen=True, slots=True)
class SupplierContactSuggestion:
    contact_type: str
    value: str
    confidence: float
    source_url: str
    contact_name: str | None = None
    role: str | None = None


@dataclass(frozen=True, slots=True)
class SupplierSuggestion:
    legal_name: str | None
    trade_name: str | None
    website: str | None
    category: str | None
    country: str | None
    city: str | None
    description: str | None
    source_url: str
    source_title: str | None = None
    source_type: str = "search_result"
    source_excerpt: str | None = None
    contacts: tuple[SupplierContactSuggestion, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SupplierSearchRequest:
    tender_id: UUID
    product: SupplierSearchProduct
    country: str | None
    max_results: int


@dataclass(frozen=True, slots=True)
class SupplierSearchResponse:
    suggestions: tuple[SupplierSuggestion, ...]
    provider_errors: tuple[str, ...] = field(default_factory=tuple)


class SupplierSearchService(ABC):
    @property
    @abstractmethod
    def provider_name(self) -> str: ...

    @property
    @abstractmethod
    def provider_version(self) -> str: ...

    @abstractmethod
    def search(self, request: SupplierSearchRequest) -> SupplierSearchResponse: ...
