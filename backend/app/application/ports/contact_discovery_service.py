from abc import ABC, abstractmethod

from app.application.ports.supplier_search_service import (
    SupplierContactSuggestion,
    SupplierSuggestion,
)


class ContactDiscoveryService(ABC):
    """Port for extracting only already-public contact data from a candidate source."""

    @property
    @abstractmethod
    def provider_name(self) -> str: ...

    @property
    @abstractmethod
    def provider_version(self) -> str: ...

    @abstractmethod
    def discover(self, suggestion: SupplierSuggestion) -> tuple[SupplierContactSuggestion, ...]: ...
