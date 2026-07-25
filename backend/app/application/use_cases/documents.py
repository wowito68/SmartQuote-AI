import logging
from contextlib import suppress
from uuid import UUID, uuid4

from app.application.dtos.document import (
    DownloadTenderDocumentResponse,
    TenderDocumentListResponse,
    TenderDocumentResponse,
    UploadTenderDocumentRequest,
)
from app.application.exceptions import TenderNotFound
from app.application.ports.document_processing_queue import DocumentProcessingQueue
from app.application.ports.file_storage import FileStorage
from app.application.ports.file_threat_scanner import FileThreatScanner
from app.application.ports.unit_of_work import UnitOfWorkFactory
from app.application.services.document_validation import DocumentFileValidator
from app.domain.documents.entities import PDF_MIME_TYPE, TenderDocument
from app.domain.documents.events import (
    DocumentDeleted,
    DocumentUploaded,
    DuplicateDocumentDetected,
    document_queued,
)
from app.domain.documents.exceptions import (
    DocumentAlreadyDeleted,
    DocumentNotFound,
    DocumentUploaderNotFound,
    DuplicateDocument,
)
from app.domain.tenders.value_objects import TenderStatus

logger = logging.getLogger(__name__)


class UploadTenderDocument:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        file_storage: FileStorage,
        *,
        maximum_size_bytes: int,
        maximum_files_per_upload: int,
        file_threat_scanner: FileThreatScanner | None = None,
        processing_queue: DocumentProcessingQueue | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._file_storage = file_storage
        self._file_threat_scanner = file_threat_scanner
        self._processing_queue = processing_queue
        self._validator = DocumentFileValidator(
            maximum_size_bytes=maximum_size_bytes,
            maximum_files_per_upload=maximum_files_per_upload,
        )

    def execute(
        self,
        tender_id: UUID,
        request: UploadTenderDocumentRequest,
    ) -> TenderDocumentListResponse:
        validated_files = self._validator.validate_many(request.files)
        if self._file_threat_scanner is not None:
            for file in validated_files:
                self._file_threat_scanner.scan(file.original_file_name, file.content)
        stored_keys: list[str] = []

        with self._uow_factory() as uow:
            tender = uow.tenders.get_by_id(tender_id, include_archived=True)
            if tender is None:
                raise TenderNotFound("Tender was not found.")
            tender.ensure_accepts_documents()
            if not uow.users.exists(request.uploaded_by_user_id):
                raise DocumentUploaderNotFound("Document uploader does not exist.")

            seen_hashes: set[str] = set()
            for file in validated_files:
                if file.file_hash.value in seen_hashes or uow.documents.find_by_hash(
                    tender_id,
                    file.file_hash,
                    include_deleted=True,
                ):
                    uow.audit_events.append(
                        DuplicateDocumentDetected(
                            tender_id=tender_id,
                            uploaded_by_user_id=request.uploaded_by_user_id,
                            file_hash=file.file_hash.value,
                            original_file_name=file.original_file_name,
                        )
                    )
                    uow.commit()
                    raise DuplicateDocument(
                        "The same document already exists within this tender."
                    )
                seen_hashes.add(file.file_hash.value)

            created_documents: list[TenderDocument] = []
            created_responses: list[TenderDocumentResponse] = []
            try:
                for file in validated_files:
                    document_id = uuid4()
                    storage_key = self._file_storage.store(
                        tender_id,
                        document_id,
                        file.content,
                    )
                    stored_keys.append(storage_key)
                    document = TenderDocument(
                        id=document_id,
                        tender_id=tender_id,
                        original_file_name=file.original_file_name,
                        storage_key=storage_key,
                        mime_type=PDF_MIME_TYPE,
                        file_size=file.file_size,
                        file_hash=file.file_hash,
                        uploaded_by_user_id=request.uploaded_by_user_id,
                    )
                    created = uow.documents.create(document)
                    uow.audit_events.append(
                        DocumentUploaded(
                            document_id=created.id,
                            tender_id=tender_id,
                            uploaded_by_user_id=request.uploaded_by_user_id,
                            file_hash=created.file_hash.value,
                        )
                    )
                    created_responses.append(TenderDocumentResponse.from_entity(created))
                    if self._processing_queue is not None:
                        created.mark_queued()
                        created = uow.documents.update(created)
                        uow.audit_events.append(
                            document_queued(created.id, file_hash=created.file_hash.value)
                        )
                    created_documents.append(created)

                if tender.status is TenderStatus.DRAFT:
                    tender.change_status(TenderStatus.DOCUMENTS_PENDING)
                    uow.tenders.update(tender)
                uow.commit()
            except Exception:
                uow.rollback()
                for storage_key in stored_keys:
                    with suppress(Exception):
                        self._file_storage.delete(storage_key)
                raise

        if self._processing_queue is not None:
            for document in created_documents:
                try:
                    self._processing_queue.enqueue(document.id)
                except Exception:
                    logger.exception(
                        "document_queue_publish_failed",
                        extra={"document_id": str(document.id)},
                    )

        items = tuple(created_responses)
        return TenderDocumentListResponse(items=items, total=len(items))


class GetTenderDocument:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, document_id: UUID) -> TenderDocumentResponse:
        with self._uow_factory() as uow:
            document = uow.documents.get_by_id(document_id)
            if document is None:
                raise DocumentNotFound("Document was not found.")
        return TenderDocumentResponse.from_entity(document)


class ListTenderDocuments:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, tender_id: UUID) -> TenderDocumentListResponse:
        with self._uow_factory() as uow:
            tender = uow.tenders.get_by_id(tender_id)
            if tender is None:
                raise TenderNotFound("Tender was not found.")
            documents = uow.documents.list_by_tender(tender_id)
        items = tuple(TenderDocumentResponse.from_entity(item) for item in documents)
        return TenderDocumentListResponse(items=items, total=len(items))


class DeleteTenderDocument:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, document_id: UUID, deleted_by_user_id: UUID) -> None:
        with self._uow_factory() as uow:
            document = uow.documents.get_by_id(document_id, include_deleted=True)
            if document is None:
                raise DocumentNotFound("Document was not found.")
            if document.is_deleted:
                raise DocumentAlreadyDeleted("Document is already deleted.")
            if not uow.users.exists(deleted_by_user_id):
                raise DocumentUploaderNotFound("Document deletion actor does not exist.")
            document.mark_deleted()
            updated = uow.documents.update(document)
            uow.audit_events.append(
                DocumentDeleted(
                    document_id=updated.id,
                    tender_id=updated.tender_id,
                    deleted_by_user_id=deleted_by_user_id,
                    file_hash=updated.file_hash.value,
                )
            )
            uow.commit()


class DownloadTenderDocument:
    def __init__(self, uow_factory: UnitOfWorkFactory, file_storage: FileStorage) -> None:
        self._uow_factory = uow_factory
        self._file_storage = file_storage

    def execute(self, document_id: UUID) -> DownloadTenderDocumentResponse:
        with self._uow_factory() as uow:
            document = uow.documents.get_by_id(document_id)
            if document is None:
                raise DocumentNotFound("Document was not found.")
        return DownloadTenderDocumentResponse(
            original_file_name=document.original_file_name,
            mime_type=document.mime_type,
            content=self._file_storage.read(document.storage_key),
        )
