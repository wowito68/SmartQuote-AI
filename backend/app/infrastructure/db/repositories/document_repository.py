from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.application.ports.document_repository import TenderDocumentRepository
from app.domain.documents.entities import TenderDocument
from app.domain.documents.exceptions import DuplicateDocument
from app.domain.documents.value_objects import DocumentStatus, FileHash
from app.infrastructure.db.mappers.document_mapper import (
    tender_document_to_domain,
    tender_document_to_model,
    update_tender_document_model,
)
from app.infrastructure.db.models.tender import TenderDocumentModel, TenderModel

_DUPLICATE_DOCUMENT_CONSTRAINT = "uq_tender_documents_tender_file_hash"
_SQLITE_DUPLICATE_SIGNATURE = (
    "UNIQUE constraint failed: tender_documents.tender_id, tender_documents.file_hash"
)


def _is_duplicate_document_violation(error: IntegrityError) -> bool:
    diagnostic = getattr(error.orig, "diag", None)
    constraint_name = getattr(diagnostic, "constraint_name", None)
    if constraint_name == _DUPLICATE_DOCUMENT_CONSTRAINT:
        return True
    message = str(error.orig)
    return _DUPLICATE_DOCUMENT_CONSTRAINT in message or _SQLITE_DUPLICATE_SIGNATURE in message


class SqlAlchemyTenderDocumentRepository(TenderDocumentRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, document: TenderDocument) -> TenderDocument:
        model = tender_document_to_model(document)
        self._session.add(model)
        try:
            self._session.flush()
        except IntegrityError as error:
            if _is_duplicate_document_violation(error):
                raise DuplicateDocument(
                    "The same document already exists within this tender."
                ) from error
            raise
        return tender_document_to_domain(model)

    def get_by_id(
        self,
        document_id: UUID,
        *,
        include_deleted: bool = False,
        for_update: bool = False,
    ) -> TenderDocument | None:
        statement = (
            select(TenderDocumentModel)
            .join(TenderModel, TenderModel.id == TenderDocumentModel.tender_id)
            .where(
                TenderDocumentModel.id == document_id,
                TenderModel.deleted_at.is_(None),
            )
        )
        if not include_deleted:
            statement = statement.where(
                TenderDocumentModel.processing_status != DocumentStatus.DELETED.value
            )
        if for_update:
            statement = statement.with_for_update()
        model = self._session.scalars(statement).first()
        return tender_document_to_domain(model) if model else None

    def list_by_tender(self, tender_id: UUID) -> list[TenderDocument]:
        statement = (
            select(TenderDocumentModel)
            .join(TenderModel, TenderModel.id == TenderDocumentModel.tender_id)
            .where(
                TenderDocumentModel.tender_id == tender_id,
                TenderDocumentModel.processing_status != DocumentStatus.DELETED.value,
                TenderModel.deleted_at.is_(None),
            )
            .order_by(TenderDocumentModel.created_at.desc())
        )
        return [tender_document_to_domain(model) for model in self._session.scalars(statement)]

    def list_by_statuses(
        self,
        statuses: set[DocumentStatus],
        *,
        limit: int = 100,
    ) -> list[TenderDocument]:
        values = [status.value for status in statuses]
        statement = (
            select(TenderDocumentModel)
            .join(TenderModel, TenderModel.id == TenderDocumentModel.tender_id)
            .where(
                TenderDocumentModel.processing_status.in_(values),
                TenderModel.deleted_at.is_(None),
            )
            .order_by(TenderDocumentModel.created_at)
            .limit(limit)
        )
        return [tender_document_to_domain(model) for model in self._session.scalars(statement)]

    def find_by_hash(
        self,
        tender_id: UUID,
        file_hash: FileHash,
        *,
        include_deleted: bool = True,
    ) -> TenderDocument | None:
        statement = select(TenderDocumentModel).where(
            TenderDocumentModel.tender_id == tender_id,
            TenderDocumentModel.file_hash == file_hash.value,
        )
        if not include_deleted:
            statement = statement.where(
                TenderDocumentModel.processing_status != DocumentStatus.DELETED.value
            )
        model = self._session.scalars(statement).first()
        return tender_document_to_domain(model) if model else None

    def update(self, document: TenderDocument) -> TenderDocument:
        model = self._session.get(TenderDocumentModel, document.id)
        if model is None:
            raise ValueError("Tender document does not exist.")
        update_tender_document_model(model, document)
        self._session.flush()
        return tender_document_to_domain(model)
