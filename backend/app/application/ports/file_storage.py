from abc import ABC, abstractmethod
from uuid import UUID


class FileStorage(ABC):
    @abstractmethod
    def store(self, tender_id: UUID, document_id: UUID, content: bytes) -> str:
        """Store content privately and return an opaque relative storage key."""
        raise NotImplementedError

    @abstractmethod
    def read(self, storage_key: str) -> bytes:
        raise NotImplementedError

    @abstractmethod
    def exists(self, storage_key: str) -> bool:
        """Return whether the opaque storage key resolves to an existing file."""
        raise NotImplementedError

    @abstractmethod
    def delete(self, storage_key: str) -> None:
        raise NotImplementedError
