from abc import ABC, abstractmethod
from uuid import UUID


class AIExtractionQueue(ABC):
    @abstractmethod
    def enqueue(self, run_id: UUID) -> None:
        raise NotImplementedError
