from abc import ABC, abstractmethod
from uuid import UUID

from app.domain.documents.processing import DocumentPage, DocumentQuality, ExtractionRun


class ExtractionRepository(ABC):
    @abstractmethod
    def create_run(self, run: ExtractionRun) -> ExtractionRun:
        raise NotImplementedError

    @abstractmethod
    def update_run(self, run: ExtractionRun) -> ExtractionRun:
        raise NotImplementedError

    @abstractmethod
    def get_run(self, run_id: UUID) -> ExtractionRun | None:
        raise NotImplementedError

    @abstractmethod
    def get_latest_run(self, document_id: UUID) -> ExtractionRun | None:
        raise NotImplementedError

    @abstractmethod
    def get_by_processing_key(
        self, document_id: UUID, processing_key: str
    ) -> ExtractionRun | None:
        raise NotImplementedError

    @abstractmethod
    def get_completed_by_processing_key(
        self, document_id: UUID, processing_key: str
    ) -> ExtractionRun | None:
        raise NotImplementedError

    @abstractmethod
    def replace_pages(self, run_id: UUID, pages: list[DocumentPage]) -> None:
        raise NotImplementedError

    @abstractmethod
    def list_pages(self, document_id: UUID) -> list[DocumentPage]:
        raise NotImplementedError

    @abstractmethod
    def list_pages_by_run(self, run_id: UUID) -> list[DocumentPage]:
        raise NotImplementedError

    @abstractmethod
    def save_quality(self, quality: DocumentQuality) -> DocumentQuality:
        raise NotImplementedError

    @abstractmethod
    def get_quality(self, document_id: UUID) -> DocumentQuality | None:
        raise NotImplementedError

    @abstractmethod
    def get_quality_by_run(self, run_id: UUID) -> DocumentQuality | None:
        raise NotImplementedError
