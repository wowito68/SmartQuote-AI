from abc import ABC, abstractmethod
from uuid import UUID

from app.domain.catalog.entities import (
    AIExtractionRun,
    CatalogProduct,
    CatalogSnapshot,
    EvidenceReference,
    ExtractedEvidence,
)
from app.domain.catalog.value_objects import ProductStatus


class CatalogRepository(ABC):
    @abstractmethod
    def create_run(self, run: AIExtractionRun) -> AIExtractionRun: ...

    @abstractmethod
    def update_run(self, run: AIExtractionRun) -> AIExtractionRun: ...

    @abstractmethod
    def get_run(self, run_id: UUID, *, for_update: bool = False) -> AIExtractionRun | None: ...

    @abstractmethod
    def get_run_by_idempotency(self, document_id: UUID, key: str) -> AIExtractionRun | None: ...

    @abstractmethod
    def list_runs(self, tender_id: UUID) -> list[AIExtractionRun]: ...

    @abstractmethod
    def create_product(self, product: CatalogProduct) -> CatalogProduct: ...

    @abstractmethod
    def update_product(self, product: CatalogProduct) -> CatalogProduct: ...

    @abstractmethod
    def get_product(self, product_id: UUID) -> CatalogProduct | None: ...

    @abstractmethod
    def list_products(self, tender_id: UUID) -> list[CatalogProduct]: ...

    @abstractmethod
    def list_products_by_run(self, run_id: UUID) -> list[CatalogProduct]: ...

    @abstractmethod
    def list_products_by_status(
        self, tender_id: UUID, statuses: set[ProductStatus]
    ) -> list[CatalogProduct]: ...

    @abstractmethod
    def add_revision(
        self,
        product_id: UUID,
        changed_by_user_id: UUID,
        before: dict,
        after: dict,
        changed_fields: list[str],
    ) -> None: ...

    @abstractmethod
    def add_evidence(
        self, evidence: ExtractedEvidence, reference: EvidenceReference
    ) -> None: ...

    @abstractmethod
    def list_evidence(
        self, product_id: UUID
    ) -> list[tuple[ExtractedEvidence, EvidenceReference]]: ...

    @abstractmethod
    def create_snapshot(self, snapshot: CatalogSnapshot) -> CatalogSnapshot: ...

    @abstractmethod
    def get_latest_snapshot(self, tender_id: UUID) -> CatalogSnapshot | None: ...
