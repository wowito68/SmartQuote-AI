import logging
from uuid import UUID

from app.application.services.document_quality import (
    DocumentQualityEvaluator,
    QualityThresholds,
)
from app.application.services.extraction_strategy import (
    ExtractionPolicy,
    FallbackDocumentTextExtractor,
)
from app.application.use_cases.document_processing import (
    DetectPendingDocuments,
    EvaluateDocumentQuality,
    ExtractDocumentText,
    FinalizeDocumentProcessing,
    MarkDocumentProcessingFailed,
    ValidateDocumentForProcessing,
)
from app.config.settings import get_settings
from app.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork
from app.infrastructure.extraction.pdfplumber_extractor import PdfPlumberExtractor
from app.infrastructure.extraction.pymupdf_extractor import PyMuPDFExtractor
from app.infrastructure.observability.logging import configure_logging
from app.infrastructure.storage.local_file_storage import LocalFileStorage
from app.infrastructure.tasks.celery_app import celery_app
from app.infrastructure.tasks.processing_queue import CeleryDocumentProcessingQueue

configure_logging()
logger = logging.getLogger(__name__)


def _components():
    settings = get_settings()
    storage = LocalFileStorage(settings.storage_root)
    extractor = FallbackDocumentTextExtractor(
        PyMuPDFExtractor(),
        PdfPlumberExtractor(),
        ExtractionPolicy(
            minimum_characters=settings.extraction_minimum_characters,
            maximum_empty_page_percentage=(
                settings.extraction_maximum_empty_page_percentage
            ),
            minimum_characters_per_page=(
                settings.extraction_minimum_characters_per_page
            ),
        ),
    )
    evaluator = DocumentQualityEvaluator(
        QualityThresholds(
            ready_minimum_characters=settings.quality_ready_minimum_characters,
            ready_maximum_empty_page_percentage=(
                settings.quality_ready_maximum_empty_page_percentage
            ),
            ready_minimum_density=settings.quality_ready_minimum_density,
            ocr_maximum_characters=settings.quality_ocr_maximum_characters,
            ocr_minimum_empty_page_percentage=(
                settings.quality_ocr_minimum_empty_page_percentage
            ),
            ocr_maximum_density=settings.quality_ocr_maximum_density,
        )
    )
    return storage, extractor, evaluator


def _run_stage(document_id: str, stage) -> str:
    parsed_id = UUID(document_id)
    try:
        stage(parsed_id)
        return document_id
    except Exception as error:
        logger.exception(
            "document_pipeline_stage_failed",
            extra={"document_id": document_id},
        )
        MarkDocumentProcessingFailed(SqlAlchemyUnitOfWork).execute(parsed_id, error)
        raise


@celery_app.task(name="smartquote.documents.start_pipeline")
def start_pipeline(document_id: str) -> str:
    parsed_id = UUID(document_id)
    storage, extractor, evaluator = _components()
    try:
        claimed = ValidateDocumentForProcessing(
            SqlAlchemyUnitOfWork,
            storage,
        ).execute(parsed_id)
        if not claimed:
            logger.info(
                "document_pipeline_duplicate_skipped",
                extra={"document_id": document_id},
            )
            return document_id
        ExtractDocumentText(
            SqlAlchemyUnitOfWork,
            storage,
            extractor,
        ).execute(parsed_id)
        EvaluateDocumentQuality(
            SqlAlchemyUnitOfWork,
            evaluator,
        ).execute(parsed_id)
        FinalizeDocumentProcessing(SqlAlchemyUnitOfWork).execute(parsed_id)
        logger.info("document_pipeline_completed", extra={"document_id": document_id})
        return document_id
    except Exception as error:
        logger.exception(
            "document_pipeline_failed",
            extra={"document_id": document_id},
        )
        MarkDocumentProcessingFailed(SqlAlchemyUnitOfWork).execute(parsed_id, error)
        raise


@celery_app.task(name="smartquote.documents.validate")
def validate_document(document_id: str) -> str:
    storage, _, _ = _components()
    return _run_stage(
        document_id,
        lambda parsed: ValidateDocumentForProcessing(
            SqlAlchemyUnitOfWork, storage
        ).execute(parsed),
    )


@celery_app.task(name="smartquote.documents.extract_text")
def extract_text(document_id: str) -> str:
    storage, extractor, _ = _components()
    return _run_stage(
        document_id,
        lambda parsed: ExtractDocumentText(
            SqlAlchemyUnitOfWork, storage, extractor
        ).execute(parsed),
    )


@celery_app.task(name="smartquote.documents.evaluate_quality")
def evaluate_quality(document_id: str) -> str:
    _, _, evaluator = _components()
    return _run_stage(
        document_id,
        lambda parsed: EvaluateDocumentQuality(
            SqlAlchemyUnitOfWork, evaluator
        ).execute(parsed),
    )


@celery_app.task(name="smartquote.documents.finalize")
def finalize_document(document_id: str) -> str:
    return _run_stage(
        document_id,
        lambda parsed: FinalizeDocumentProcessing(SqlAlchemyUnitOfWork).execute(parsed),
    )


@celery_app.task(name="smartquote.documents.detect_pending")
def detect_pending_documents() -> int:
    return DetectPendingDocuments(
        SqlAlchemyUnitOfWork,
        CeleryDocumentProcessingQueue(),
    ).execute()
