from app.domain.documents.processing import DocumentPage, DocumentQuality, ExtractionRun
from app.domain.documents.value_objects import (
    DocumentQualityDecision,
    DocumentQualityLevel,
    ExtractionRunStatus,
)
from app.infrastructure.db.models.document_processing import (
    DocumentPageModel,
    DocumentQualityModel,
    ExtractionRunModel,
)


def run_to_model(run: ExtractionRun) -> ExtractionRunModel:
    return ExtractionRunModel(
        id=run.id,
        document_id=run.document_id,
        processing_key=run.processing_key,
        extractor_name=run.extractor_name,
        extractor_version=run.extractor_version,
        configuration=run.configuration,
        status=run.status.value,
        started_at=run.started_at,
        completed_at=run.completed_at,
        duration_ms=run.duration_ms,
        pages_processed=run.pages_processed,
        characters_extracted=run.characters_extracted,
        error_type=run.error_type,
        error_message=run.error_message,
        reused_from_run_id=run.reused_from_run_id,
        created_at=run.created_at,
    )


def run_to_domain(model: ExtractionRunModel) -> ExtractionRun:
    return ExtractionRun(
        id=model.id,
        document_id=model.document_id,
        processing_key=model.processing_key,
        extractor_name=model.extractor_name,
        extractor_version=model.extractor_version,
        configuration=model.configuration,
        status=ExtractionRunStatus(model.status),
        started_at=model.started_at,
        completed_at=model.completed_at,
        duration_ms=model.duration_ms,
        pages_processed=model.pages_processed,
        characters_extracted=model.characters_extracted,
        error_type=model.error_type,
        error_message=model.error_message,
        reused_from_run_id=model.reused_from_run_id,
        created_at=model.created_at,
    )


def update_run_model(model: ExtractionRunModel, run: ExtractionRun) -> None:
    model.extractor_name = run.extractor_name
    model.extractor_version = run.extractor_version
    model.configuration = run.configuration
    model.status = run.status.value
    model.started_at = run.started_at
    model.completed_at = run.completed_at
    model.duration_ms = run.duration_ms
    model.pages_processed = run.pages_processed
    model.characters_extracted = run.characters_extracted
    model.error_type = run.error_type
    model.error_message = run.error_message
    model.reused_from_run_id = run.reused_from_run_id


def page_to_model(page: DocumentPage) -> DocumentPageModel:
    return DocumentPageModel(
        id=page.id,
        document_id=page.document_id,
        extraction_run_id=page.extraction_run_id,
        page_number=page.page_number,
        text=page.text,
        width=page.width,
        height=page.height,
        character_count=page.character_count,
        word_count=page.word_count,
        is_empty=page.is_empty,
        text_density=page.text_density,
        duration_ms=page.duration_ms,
        created_at=page.created_at,
    )


def page_to_domain(model: DocumentPageModel) -> DocumentPage:
    return DocumentPage(
        id=model.id,
        document_id=model.document_id,
        extraction_run_id=model.extraction_run_id,
        page_number=model.page_number,
        text=model.text,
        width=model.width,
        height=model.height,
        duration_ms=model.duration_ms,
        created_at=model.created_at,
    )


def quality_to_model(quality: DocumentQuality) -> DocumentQualityModel:
    return DocumentQualityModel(
        id=quality.id,
        document_id=quality.document_id,
        extraction_run_id=quality.extraction_run_id,
        pages_processed=quality.pages_processed,
        empty_pages=quality.empty_pages,
        characters_extracted=quality.characters_extracted,
        empty_page_percentage=quality.empty_page_percentage,
        text_density=quality.text_density,
        quality_level=quality.quality_level.value,
        decision=quality.decision.value,
        requires_manual_review=quality.requires_manual_review,
        evaluated_at=quality.evaluated_at,
    )


def quality_to_domain(model: DocumentQualityModel) -> DocumentQuality:
    return DocumentQuality(
        id=model.id,
        document_id=model.document_id,
        extraction_run_id=model.extraction_run_id,
        pages_processed=model.pages_processed,
        empty_pages=model.empty_pages,
        characters_extracted=model.characters_extracted,
        empty_page_percentage=model.empty_page_percentage,
        text_density=model.text_density,
        quality_level=DocumentQualityLevel(model.quality_level),
        decision=DocumentQualityDecision(model.decision),
        requires_manual_review=model.requires_manual_review,
        evaluated_at=model.evaluated_at,
    )
