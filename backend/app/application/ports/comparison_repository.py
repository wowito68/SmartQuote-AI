from abc import ABC, abstractmethod
from uuid import UUID

from app.domain.comparison.entities import Comparison


class ComparisonRepository(ABC):
    @abstractmethod
    def create(self, comparison: Comparison) -> Comparison: ...

    @abstractmethod
    def get(self, comparison_id: UUID) -> Comparison | None: ...

    @abstractmethod
    def get_by_key(self, tender_id: UUID, comparison_key: str) -> Comparison | None: ...

    @abstractmethod
    def get_latest(self, tender_id: UUID) -> Comparison | None: ...
