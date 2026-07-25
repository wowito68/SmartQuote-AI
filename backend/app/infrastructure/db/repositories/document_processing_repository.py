from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.application.ports.extraction_repository import ExtractionRepository
from app.domain.documents.processing import DocumentPage, DocumentQuality, ExtractionRun
from app.domain.documents.value_objects import ExtractionRunStatus
from app.infrastructure.db.mappers.document_processing_mapper import (
    page_to_domain,
    page_to_model,
    quality_to_domain,
    quality_to_model,
    run_to_domain,
    run_to_model,
    update_run_model,
)
from app.infrastructure.db.models.document_processing import (
    DocumentPageModel,
    DocumentQualityModel,
    ExtractionRunModel,
)


class SqlAlchemyExtractionRepository(ExtractionRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_run(self, run: ExtractionRun) -> ExtractionRun:
        model = run_to_model(run)
        self._session.add(model)
        self._session.flush()
        return run_to_domain(model)

    def update_run(self, run: ExtractionRun) -> ExtractionRun:
        model = self._session.get(ExtractionRunModel, run.id)
        if model is None:
            raise ValueError("Extraction run does not exist.")
        update_run_model(model, run)
        self._session.flush()
        return run_to_domain(model)

    def get_run(self, run_id: UUID) -> ExtractionRun | None:
        model = self._session.get(ExtractionRunModel, run_id)
        return run_to_domain(model) if model else None

    def get_latest_run(self, document_id: UUID) -> ExtractionRun | None:
        statement = (
            select(ExtractionRunModel)
            .where(ExtractionRunModel.document_id == document_id)
            .order_by(ExtractionRunModel.created_at.desc())
        )
        model = self._session.scalars(statement).first()
        return run_to_domain(model) if model else None

    def get_by_processing_key(
        self, document_id: UUID, processing_key: str
    ) -> ExtractionRun | None:
        statement = select(ExtractionRunModel).where(
            ExtractionRunModel.document_id == document_id,
            ExtractionRunModel.processing_key == processing_key,
        )
        model = self._session.scalars(statement).first()
        return run_to_domain(model) if model else None

    def get_completed_by_processing_key(
        self, document_id: UUID, processing_key: str
    ) -> ExtractionRun | None:
        statement = select(ExtractionRunModel).where(
            ExtractionRunModel.document_id == document_id,
            ExtractionRunModel.processing_key == processing_key,
            ExtractionRunModel.status.in_(
                [ExtractionRunStatus.COMPLETED.value, ExtractionRunStatus.REUSED.value]
            ),
        )
        model = self._session.scalars(statement).first()
        return run_to_domain(model) if model else None

    def replace_pages(self, run_id: UUID, pages: list[DocumentPage]) -> None:
        self._session.execute(
            delete(DocumentPageModel).where(DocumentPageModel.extraction_run_id == run_id)
        )
        self._session.add_all(page_to_model(page) for page in pages)
        self._session.flush()

    def list_pages(self, document_id: UUID) -> list[DocumentPage]:
        latest = self.get_latest_run(document_id)
        return self.list_pages_by_run(latest.id) if latest else []

    def list_pages_by_run(self, run_id: UUID) -> list[DocumentPage]:
        statement = (
            select(DocumentPageModel)
            .where(DocumentPageModel.extraction_run_id == run_id)
            .order_by(DocumentPageModel.page_number)
        )
        return [page_to_domain(model) for model in self._session.scalars(statement)]

    def save_quality(self, quality: DocumentQuality) -> DocumentQuality:
        model = quality_to_model(quality)
        self._session.add(model)
        self._session.flush()
        return quality_to_domain(model)

    def get_quality(self, document_id: UUID) -> DocumentQuality | None:
        statement = (
            select(DocumentQualityModel)
            .where(DocumentQualityModel.document_id == document_id)
            .order_by(DocumentQualityModel.evaluated_at.desc())
        )
        model = self._session.scalars(statement).first()
        return quality_to_domain(model) if model else None

    def get_quality_by_run(self, run_id: UUID) -> DocumentQuality | None:
        statement = select(DocumentQualityModel).where(
            DocumentQualityModel.extraction_run_id == run_id
        )
        model = self._session.scalars(statement).first()
        return quality_to_domain(model) if model else None
