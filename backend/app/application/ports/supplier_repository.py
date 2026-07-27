from abc import ABC, abstractmethod
from uuid import UUID

from app.domain.suppliers.entities import (
    ProductSupplierMatch,
    Supplier,
    SupplierContact,
    SupplierDiscoveryRun,
    SupplierMergeSuggestion,
    SupplierSource,
    TenderSupplier,
)


class SupplierRepository(ABC):
    @abstractmethod
    def create_run(self, run: SupplierDiscoveryRun) -> SupplierDiscoveryRun: ...

    @abstractmethod
    def update_run(self, run: SupplierDiscoveryRun) -> SupplierDiscoveryRun: ...

    @abstractmethod
    def get_run(
        self, run_id: UUID, *, for_update: bool = False
    ) -> SupplierDiscoveryRun | None: ...

    @abstractmethod
    def get_run_by_idempotency(
        self, tender_id: UUID, key: str
    ) -> SupplierDiscoveryRun | None: ...

    @abstractmethod
    def list_runs(self, tender_id: UUID) -> list[SupplierDiscoveryRun]: ...

    @abstractmethod
    def create_supplier(self, supplier: Supplier) -> Supplier: ...

    @abstractmethod
    def update_supplier(self, supplier: Supplier) -> Supplier: ...

    @abstractmethod
    def get_supplier(self, supplier_id: UUID) -> Supplier | None: ...

    @abstractmethod
    def list_suppliers(self) -> list[Supplier]: ...

    @abstractmethod
    def add_contact(self, contact: SupplierContact) -> SupplierContact: ...

    @abstractmethod
    def list_contacts(self, supplier_id: UUID) -> list[SupplierContact]: ...

    @abstractmethod
    def contact_exists(self, supplier_id: UUID, identity_key: str) -> bool: ...

    @abstractmethod
    def add_source(self, source: SupplierSource) -> SupplierSource: ...

    @abstractmethod
    def list_sources(self, supplier_id: UUID) -> list[SupplierSource]: ...

    @abstractmethod
    def source_exists(self, supplier_id: UUID, source_url: str) -> bool: ...

    @abstractmethod
    def create_tender_supplier(self, tender_supplier: TenderSupplier) -> TenderSupplier: ...

    @abstractmethod
    def update_tender_supplier(self, tender_supplier: TenderSupplier) -> TenderSupplier: ...

    @abstractmethod
    def get_tender_supplier(self, tender_supplier_id: UUID) -> TenderSupplier | None: ...

    @abstractmethod
    def find_tender_supplier(
        self, tender_id: UUID, supplier_id: UUID
    ) -> TenderSupplier | None: ...

    @abstractmethod
    def list_tender_suppliers(self, tender_id: UUID) -> list[TenderSupplier]: ...

    @abstractmethod
    def create_match(self, match: ProductSupplierMatch) -> ProductSupplierMatch: ...

    @abstractmethod
    def update_match(self, match: ProductSupplierMatch) -> ProductSupplierMatch: ...

    @abstractmethod
    def get_match(
        self, tender_supplier_id: UUID, product_id: UUID
    ) -> ProductSupplierMatch | None: ...

    @abstractmethod
    def list_matches(self, tender_supplier_id: UUID) -> list[ProductSupplierMatch]: ...

    @abstractmethod
    def create_merge_suggestion(
        self, suggestion: SupplierMergeSuggestion
    ) -> SupplierMergeSuggestion: ...

    @abstractmethod
    def update_merge_suggestion(
        self, suggestion: SupplierMergeSuggestion
    ) -> SupplierMergeSuggestion: ...

    @abstractmethod
    def get_merge_suggestion(
        self, suggestion_id: UUID
    ) -> SupplierMergeSuggestion | None: ...

    @abstractmethod
    def find_merge_suggestion(
        self, source_supplier_id: UUID, target_supplier_id: UUID
    ) -> SupplierMergeSuggestion | None: ...

    @abstractmethod
    def list_merge_suggestions(
        self, supplier_id: UUID
    ) -> list[SupplierMergeSuggestion]: ...
