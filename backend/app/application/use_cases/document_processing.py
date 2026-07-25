import hashlib
import logging
from uuid import UUID

from app.application.dtos.document_processing import (
    DocumentPageListResponse,
    DocumentPageResponse,
    DocumentQualityResponse,
    DocumentStatusResponse,
    ExtractionRunResponse,
)
from app.application.ports.document_processing_queue import DocumentProcessingQueue
from app.application.ports.file_storage import FileStorage
from app.application.ports.unit_of_work import UnitOfWorkFactory
from app.application.services.document_quality import DocumentQualityEvaluator
from app.application.services.extraction_strategy import FallbackDocumentTextExtractor
from app.domain.documents.entities import TenderDocument
from app.domain.documents.events import (
    document_marked_for_ocr,
    document_processing_failed,
    document_processing_started,
    document_queued,
    document_ready_for_ai,
    quality_evaluation_completed,
    text_extraction_completed,
)
from app.domain.documents.exceptions import (
    DocumentExtractionFailure,
    DocumentExtractionNotFound,
    DocumentNotFound,
    DocumentQualityNotFound,
    InvalidDocumentFile,
)
from app.domain.documents.processing import DocumentPage, ExtractionRun
from app.domain.documents.value_objects import (
    DocumentQualityDecision,
    DocumentStatus,
    ExtractionRunStatus,
)

logger = logging.getLogger(__name__)


class QueueDocumentProcessing:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        queue: DocumentProcessingQueue,
    ) -> None:
        self._uow_factory = uow_factory
        self._queue = queue

    def execute(self, document_id: UUID) -> DocumentStatusResponse:
        with self._uow_factory() as uow:
            document = self._get_document(uow, document_id)
            if document.status in {DocumentStatus.UPLOADED, DocumentStatus.FAILED}:
                document.mark_queued()
                uow.documents.update(document)
                uow.audit_events.append(
                    document_queued(document.id, file_hash=document.file_hash.value)
                )
                uow.commit()
            response = _status_response(document)

        self._queue.enqueue(document_id)
        return response

    @staticmethod
    def _get_document(uow, document_id: UUID) -> TenderDocument:
        document = uow.documents.get_by_id(document_id, include_deleted=True)
        if document is None:
            raise DocumentNotFound("Document was not found.")
        return document


class DetectPendingDocuments:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        queue: DocumentProcessingQueue,
    ) -> None:
        self._uow_factory = uow_factory
        self._queue = queue

    def execute(self, *, limit: int = 100) -> int:
        with self._uow_factory() as uow:
            pending = uow.documents.list_by_statuses(
                {DocumentStatus.UPLOADED, DocumentStatus.QUEUED}, limit=limit
            )
            queued: list[UUID] = []
            for document in pending:
                if document.status is DocumentStatus.UPLOADED:
                    document.mark_queued()
                    uow.documents.update(document)
                    uow.audit_events.append(
                        document_queued(document.id, file_hash=document.file_hash.value)
                    )
                queued.append(document.id)
            uow.commit()

        for document_id in queued:
            self._queue.enqueue(document_id)
        logger.info("pending_documents_queued", extra={"pending_count": len(queued)})
        return len(queued)


class ValidateDocumentForProcessing:
    def __init__(self, uow_factory: UnitOfWorkFactory, file_storage: FileStorage) -> None:
        self._uow_factory = uow_factory
        self._file_storage = file_storage

    def execute(self, document_id: UUID) -> bool:
        with self._uow_factory() as uow:
            document = _required_document(uow, document_id, for_update=True)
            if document.status in {
                DocumentStatus.PROCESSING,
                DocumentStatus.TEXT_EXTRACTED,
                DocumentStatus.READY_FOR_AI,
                DocumentStatus.NEEDS_OCR,
            }:
                return False
            content = self._file_storage.read(document.storage_key)
            if not content.startswith(b"%PDF-"):
                self._fail(uow, document, InvalidDocumentFile("Stored file is not a PDF."))
            actual_hash = hashlib.sha256(content).hexdigest()
            if actual_hash != document.file_hash.value:
                self._fail(uow, document, InvalidDocumentFile("Stored file hash does not match."))
            document.start_processing()
            uow.documents.update(document)
            uow.audit_events.append(document_processing_started(document.id))
            uow.commit()
            return True

    @staticmethod
    def _fail(uow, document: TenderDocument, error: Exception) -> None:
        document.mark_failed(str(error))
        uow.documents.update(document)
        uow.audit_events.append(
            document_processing_failed(
                document.id,
                error_type=type(error).__name__,
                error_message=str(error),
            )
        )
        uow.commit()
        raise error


class ExtractDocumentText:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        file_storage: FileStorage,
        extractor: FallbackDocumentTextExtractor,
    ) -> None:
        self._uow_factory = uow_factory
        self._file_storage = file_storage
        self._extractor = extractor

    def execute(self, document_id: UUID) -> UUID:
        with self._uow_factory() as uow:
            document = _required_document(uow, document_id)
            latest = uow.extractions.get_latest_run(document.id)
            if document.status in {
                DocumentStatus.TEXT_EXTRACTED,
                DocumentStatus.READY_FOR_AI,
                DocumentStatus.NEEDS_OCR,
            } and latest is not None:
                return document.id
            processing_key = self._extractor.processing_key(document.file_hash.value)
            completed = uow.extractions.get_completed_by_processing_key(
                document.id, processing_key
            )
            if completed is not None:
                document.mark_text_extracted()
                uow.documents.update(document)
                uow.audit_events.append(
                    text_extraction_completed(
                        document.id,
                        extraction_run_id=completed.id,
                        extractor_name=completed.extractor_name,
                        extractor_version=completed.extractor_version,
                        pages_processed=completed.pages_processed,
                        characters_extracted=completed.characters_extracted,
                        duration_ms=completed.duration_ms or 0,
                        reused=True,
                    )
                )
                uow.commit()
                return document.id

            existing_run = uow.extractions.get_by_processing_key(document.id, processing_key)
            if existing_run is not None:
                existing_run.restart()
                existing_run.extractor_name = "pending"
                existing_run.extractor_version = self._extractor.strategy_version
                existing_run.configuration = self._extractor.configuration()
                run = uow.extractions.update_run(existing_run)
            else:
                run = ExtractionRun(
                    document_id=document.id,
                    processing_key=processing_key,
                    extractor_name="pending",
                    extractor_version=self._extractor.strategy_version,
                    configuration=self._extractor.configuration(),
                )
                run = uow.extractions.create_run(run)
            storage_key = document.storage_key
            uow.commit()

        try:
            result = self._extractor.extract(self._file_storage.read(storage_key))
            pages = [
                DocumentPage(
                    document_id=document_id,
                    extraction_run_id=run.id,
                    page_number=page.page_number,
                    text=page.text,
                    width=page.width,
                    height=page.height,
                    duration_ms=page.duration_ms,
                )
                for page in result.pages
            ]
            for page in pages:
                logger.info(
                    "document_page_text_extracted",
                    extra={
                        "document_id": str(document_id),
                        "extraction_run_id": str(run.id),
                        "extractor_name": result.extractor_name,
                        "page_number": page.page_number,
                        "duration_ms": page.duration_ms,
                        "characters_extracted": page.character_count,
                    },
                )
            logger.info(
                "document_text_extracted",
                extra={
                    "document_id": str(document_id),
                    "extraction_run_id": str(run.id),
                    "extractor_name": result.extractor_name,
                    "duration_ms": result.duration_ms,
                    "pages_processed": len(pages),
                    "characters_extracted": sum(page.character_count for page in pages),
                },
            )
            with self._uow_factory() as uow:
                current_run = uow.extractions.get_run(run.id)
                document = _required_document(uow, document_id)
                if current_run is None:
                    raise DocumentExtractionNotFound("Extraction run disappeared.")
                current_run.extractor_name = result.extractor_name
                current_run.extractor_version = result.extractor_version
                current_run.complete(pages, result.duration_ms)
                uow.extractions.replace_pages(current_run.id, pages)
                uow.extractions.update_run(current_run)
                document.mark_text_extracted()
                uow.documents.update(document)
                uow.audit_events.append(
                    text_extraction_completed(
                        document.id,
                        extraction_run_id=current_run.id,
                        extractor_name=current_run.extractor_name,
                        extractor_version=current_run.extractor_version,
                        pages_processed=current_run.pages_processed,
                        characters_extracted=current_run.characters_extracted,
                        duration_ms=current_run.duration_ms or 0,
                    )
                )
                uow.commit()
            return document_id
        except Exception as error:
            self._record_failure(document_id, run.id, error)
            if isinstance(error, DocumentExtractionFailure):
                raise
            raise DocumentExtractionFailure(str(error)) from error

    def _record_failure(self, document_id: UUID, run_id: UUID, error: Exception) -> None:
        with self._uow_factory() as uow:
            run = uow.extractions.get_run(run_id)
            document = uow.documents.get_by_id(document_id, include_deleted=True)
            if run is not None and run.status is ExtractionRunStatus.RUNNING:
                run.fail(error)
                uow.extractions.update_run(run)
            if document is not None and not document.is_deleted:
                document.mark_failed(str(error))
                uow.documents.update(document)
                uow.audit_events.append(
                    document_processing_failed(
                        document.id,
                        error_type=type(error).__name__,
                        error_message=str(error),
                    )
                )
            uow.commit()


class EvaluateDocumentQuality:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        evaluator: DocumentQualityEvaluator,
    ) -> None:
        self._uow_factory = uow_factory
        self._evaluator = evaluator

    def execute(self, document_id: UUID) -> UUID:
        with self._uow_factory() as uow:
            document = _required_document(uow, document_id)
            run = uow.extractions.get_latest_run(document.id)
            if run is None or run.status not in {
                ExtractionRunStatus.COMPLETED,
                ExtractionRunStatus.REUSED,
            }:
                raise DocumentExtractionNotFound("Completed extraction run was not found.")
            existing = uow.extractions.get_quality_by_run(run.id)
            if existing is not None:
                return document.id
            pages = uow.extractions.list_pages_by_run(run.id)
            quality = self._evaluator.evaluate(document.id, run.id, pages)
            quality = uow.extractions.save_quality(quality)
            uow.audit_events.append(
                quality_evaluation_completed(
                    document.id,
                    quality_id=quality.id,
                    decision=quality.decision.value,
                    empty_page_percentage=quality.empty_page_percentage,
                    text_density=quality.text_density,
                )
            )
            logger.info(
                "document_quality_evaluated",
                extra={
                    "document_id": str(document.id),
                    "extraction_run_id": str(run.id),
                    "pages_processed": quality.pages_processed,
                    "characters_extracted": quality.characters_extracted,
                    "empty_pages": quality.empty_pages,
                    "empty_page_percentage": quality.empty_page_percentage,
                    "text_density": quality.text_density,
                    "quality_decision": quality.decision.value,
                },
            )
            uow.commit()
            return document.id


class FinalizeDocumentProcessing:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, document_id: UUID) -> UUID:
        with self._uow_factory() as uow:
            document = _required_document(uow, document_id)
            if document.status in {DocumentStatus.READY_FOR_AI, DocumentStatus.NEEDS_OCR}:
                return document.id
            quality = uow.extractions.get_quality(document.id)
            if quality is None:
                raise DocumentQualityNotFound("Document quality was not found.")
            if quality.decision is DocumentQualityDecision.READY_FOR_AI:
                document.mark_ready_for_ai()
                uow.audit_events.append(document_ready_for_ai(document.id))
            else:
                document.mark_needs_ocr()
                uow.audit_events.append(
                    document_marked_for_ocr(
                        document.id,
                        requires_manual_review=quality.requires_manual_review,
                    )
                )
            uow.documents.update(document)
            logger.info(
                "document_processing_finalized",
                extra={
                    "document_id": str(document.id),
                    "document_status": document.status.value,
                    "quality_decision": quality.decision.value,
                },
            )
            uow.commit()
            return document.id


class GetDocumentProcessingStatus:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, document_id: UUID) -> DocumentStatusResponse:
        with self._uow_factory() as uow:
            return _status_response(_required_document(uow, document_id))


class ListDocumentPages:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, document_id: UUID) -> DocumentPageListResponse:
        with self._uow_factory() as uow:
            _required_document(uow, document_id)
            pages = uow.extractions.list_pages(document_id)
            if not pages:
                raise DocumentExtractionNotFound("Document pages were not found.")
        items = tuple(DocumentPageResponse.from_entity(page) for page in pages)
        return DocumentPageListResponse(items=items, total=len(items))


class GetDocumentQuality:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, document_id: UUID) -> DocumentQualityResponse:
        with self._uow_factory() as uow:
            _required_document(uow, document_id)
            quality = uow.extractions.get_quality(document_id)
            if quality is None:
                raise DocumentQualityNotFound("Document quality was not found.")
        return DocumentQualityResponse.from_entity(quality)


class GetDocumentExtraction:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, document_id: UUID) -> ExtractionRunResponse:
        with self._uow_factory() as uow:
            _required_document(uow, document_id)
            run = uow.extractions.get_latest_run(document_id)
            if run is None:
                raise DocumentExtractionNotFound("Extraction run was not found.")
        return ExtractionRunResponse.from_entity(run)


def _required_document(
    uow,
    document_id: UUID,
    *,
    for_update: bool = False,
) -> TenderDocument:
    document = uow.documents.get_by_id(
        document_id,
        include_deleted=True,
        for_update=for_update,
    )
    if document is None or document.is_deleted:
        raise DocumentNotFound("Document was not found.")
    return document


def _status_response(document: TenderDocument) -> DocumentStatusResponse:
    return DocumentStatusResponse(
        document_id=document.id,
        status=document.status,
        requires_ocr=document.requires_ocr,
        last_processing_error=document.last_processing_error,
        queued_at=document.queued_at,
        processing_started_at=document.processing_started_at,
        processed_at=document.processed_at,
    )


class MarkDocumentProcessingFailed:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, document_id: UUID, error: Exception) -> None:
        with self._uow_factory() as uow:
            document = uow.documents.get_by_id(document_id, include_deleted=True)
            if document is None or document.is_deleted:
                return
            if document.status is DocumentStatus.FAILED:
                return
            document.mark_failed(str(error))
            uow.documents.update(document)
            uow.audit_events.append(
                document_processing_failed(
                    document.id,
                    error_type=type(error).__name__,
                    error_message=str(error),
                )
            )
            uow.commit()
