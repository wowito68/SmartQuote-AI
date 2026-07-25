from abc import ABC, abstractmethod
from uuid import UUID


class DocumentProcessingQueue(ABC):
    @abstractmethod
    def enqueue(self, document_id: UUID) -> None:
        raise NotImplementedError
