from abc import ABC, abstractmethod
from uuid import UUID

from app.domain.comparisons.entities import ComparisonRun
from app.domain.quotes.entities import (
    Quote,
    QuoteDocument,
    QuoteEvidenceReference,
    QuoteExtractionRun,
    QuoteItem,
    QuoteItemRevision,
    QuoteTaskRecord,
)
from app.domain.quotes.value_objects import QuoteStatus


class QuoteRepository(ABC):
    @abstractmethod
    def create_quote(self, quote: Quote) -> Quote: ...

    @abstractmethod
    def update_quote(self, quote: Quote) -> Quote: ...

    @abstractmethod
    def get_quote(self, quote_id: UUID, *, for_update: bool = False) -> Quote | None: ...

    @abstractmethod
    def find_duplicate(self, tender_id: UUID, supplier_id: UUID, file_hash: str) -> Quote | None: ...

    @abstractmethod
    def list_quotes(self, tender_id: UUID) -> list[Quote]: ...

    @abstractmethod
    def list_quotes_by_status(self, tender_id: UUID, statuses: set[QuoteStatus]) -> list[Quote]: ...

    @abstractmethod
    def create_document(self, document: QuoteDocument) -> QuoteDocument: ...

    @abstractmethod
    def update_document(self, document: QuoteDocument) -> QuoteDocument: ...

    @abstractmethod
    def get_document(self, document_id: UUID, *, for_update: bool = False) -> QuoteDocument | None: ...

    @abstractmethod
    def list_documents(self, quote_id: UUID) -> list[QuoteDocument]: ...

    @abstractmethod
    def create_run(self, run: QuoteExtractionRun) -> QuoteExtractionRun: ...

    @abstractmethod
    def update_run(self, run: QuoteExtractionRun) -> QuoteExtractionRun: ...

    @abstractmethod
    def get_run(self, run_id: UUID, *, for_update: bool = False) -> QuoteExtractionRun | None: ...

    @abstractmethod
    def get_run_by_key(self, quote_id: UUID, key: str) -> QuoteExtractionRun | None: ...

    @abstractmethod
    def get_completed_run_by_fingerprint(self, quote_id: UUID, fingerprint: str) -> QuoteExtractionRun | None: ...

    @abstractmethod
    def list_runs(self, quote_id: UUID) -> list[QuoteExtractionRun]: ...

    @abstractmethod
    def next_run_number(self, quote_id: UUID) -> int: ...

    @abstractmethod
    def replace_items(self, quote_id: UUID, items: tuple[QuoteItem, ...]) -> tuple[QuoteItem, ...]: ...

    @abstractmethod
    def create_items(self, quote_id: UUID, items: tuple[QuoteItem, ...]) -> tuple[QuoteItem, ...]: ...

    @abstractmethod
    def supersede_current_items(self, quote_id: UUID) -> None: ...

    @abstractmethod
    def list_items(self, quote_id: UUID) -> list[QuoteItem]: ...

    @abstractmethod
    def list_items_by_run(self, run_id: UUID) -> list[QuoteItem]: ...

    @abstractmethod
    def get_item(self, item_id: UUID, *, for_update: bool = False) -> QuoteItem | None: ...

    @abstractmethod
    def update_item(self, item: QuoteItem) -> QuoteItem: ...

    @abstractmethod
    def create_evidence(self, evidence: QuoteEvidenceReference) -> QuoteEvidenceReference: ...

    @abstractmethod
    def list_evidence(self, quote_id: UUID) -> list[QuoteEvidenceReference]: ...

    @abstractmethod
    def add_item_revision(self, revision: QuoteItemRevision) -> QuoteItemRevision: ...

    @abstractmethod
    def list_item_revisions(self, quote_id: UUID) -> list[QuoteItemRevision]: ...

    @abstractmethod
    def create_task(self, task: QuoteTaskRecord) -> QuoteTaskRecord: ...

    @abstractmethod
    def update_task(self, task: QuoteTaskRecord) -> QuoteTaskRecord: ...

    @abstractmethod
    def get_task(self, task_id: UUID, *, for_update: bool = False) -> QuoteTaskRecord | None: ...

    @abstractmethod
    def get_task_by_correlation(self, correlation_id: str) -> QuoteTaskRecord | None: ...

    @abstractmethod
    def get_latest_task(self, quote_id: UUID) -> QuoteTaskRecord | None: ...

    @abstractmethod
    def create_comparison(self, comparison: ComparisonRun) -> ComparisonRun: ...

    @abstractmethod
    def get_comparison_by_key(self, tender_id: UUID, key: str) -> ComparisonRun | None: ...

    @abstractmethod
    def get_latest_comparison(self, tender_id: UUID) -> ComparisonRun | None: ...
