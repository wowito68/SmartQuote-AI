from abc import ABC, abstractmethod
from uuid import UUID


class QuoteAnalysisQueue(ABC):
    @abstractmethod
    def enqueue(
        self,
        quote_id: UUID,
        correlation_id: str | None = None,
        *,
        force: bool = False,
    ) -> None:
        raise NotImplementedError
