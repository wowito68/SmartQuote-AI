from abc import ABC, abstractmethod
from uuid import UUID

from app.domain.comparisons.entities import ComparisonRun
from app.domain.quotes.entities import Quote, QuoteExtractionRun, QuoteItem
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
    def create_run(self, run: QuoteExtractionRun) -> QuoteExtractionRun: ...

    @abstractmethod
    def update_run(self, run: QuoteExtractionRun) -> QuoteExtractionRun: ...

    @abstractmethod
    def get_run(self, run_id: UUID, *, for_update: bool = False) -> QuoteExtractionRun | None: ...

    @abstractmethod
    def get_run_by_key(self, quote_id: UUID, key: str) -> QuoteExtractionRun | None: ...

    @abstractmethod
    def replace_items(self, quote_id: UUID, items: tuple[QuoteItem, ...]) -> tuple[QuoteItem, ...]: ...

    @abstractmethod
    def list_items(self, quote_id: UUID) -> list[QuoteItem]: ...

    @abstractmethod
    def create_comparison(self, comparison: ComparisonRun) -> ComparisonRun: ...

    @abstractmethod
    def get_comparison_by_key(self, tender_id: UUID, key: str) -> ComparisonRun | None: ...

    @abstractmethod
    def get_latest_comparison(self, tender_id: UUID) -> ComparisonRun | None: ...
