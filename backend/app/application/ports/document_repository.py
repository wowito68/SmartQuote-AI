from abc import ABC, abstractmethod
from uuid import UUID

from app.domain.documents.entities import TenderDocument
from app.domain.documents.value_objects import FileHash


class TenderDocumentRepository(ABC):
    @abstractmethod
    def create(self, document: TenderDocument) -> TenderDocument:
        raise NotImplementedError

    @abstractmethod
    def get_by_id(
        self,
        document_id: UUID,
        *,
        include_deleted: bool = False,
    ) -> TenderDocument | None:
        raise NotImplementedError

    @abstractmethod
    def list_by_tender(self, tender_id: UUID) -> list[TenderDocument]:
        raise NotImplementedError

    @abstractmethod
    def find_by_hash(
        self,
        tender_id: UUID,
        file_hash: FileHash,
        *,
        include_deleted: bool = True,
    ) -> TenderDocument | None:
        raise NotImplementedError

    @abstractmethod
    def update(self, document: TenderDocument) -> TenderDocument:
        raise NotImplementedError
