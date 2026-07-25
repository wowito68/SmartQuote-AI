from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from app.domain.documents.processing import DocumentPage, DocumentQuality, ExtractionRun
from app.domain.documents.value_objects import (
    DocumentQualityDecision,
    DocumentQualityLevel,
    DocumentStatus,
    ExtractionRunStatus,
)


@dataclass(frozen=True, slots=True)
class DocumentStatusResponse:
    document_id: UUID
    status: DocumentStatus
    requires_ocr: bool
    last_processing_error: str | None
    queued_at: datetime | None
    processing_started_at: datetime | None
    processed_at: datetime | None


@dataclass(frozen=True, slots=True)
class DocumentPageResponse:
    id: UUID
    document_id: UUID
    extraction_run_id: UUID
    page_number: int
    text: str
    character_count: int
    word_count: int
    is_empty: bool
    text_density: float
    duration_ms: int

    @classmethod
    def from_entity(cls, page: DocumentPage) -> "DocumentPageResponse":
        return cls(
            id=page.id,
            document_id=page.document_id,
            extraction_run_id=page.extraction_run_id,
            page_number=page.page_number,
            text=page.text,
            character_count=page.character_count,
            word_count=page.word_count,
            is_empty=page.is_empty,
            text_density=round(page.text_density, 6),
            duration_ms=page.duration_ms,
        )


@dataclass(frozen=True, slots=True)
class DocumentPageListResponse:
    items: tuple[DocumentPageResponse, ...]
    total: int


@dataclass(frozen=True, slots=True)
class DocumentQualityResponse:
    id: UUID
    document_id: UUID
    extraction_run_id: UUID
    pages_processed: int
    empty_pages: int
    characters_extracted: int
    empty_page_percentage: float
    text_density: float
    quality_level: DocumentQualityLevel
    decision: DocumentQualityDecision
    requires_manual_review: bool
    evaluated_at: datetime

    @classmethod
    def from_entity(cls, quality: DocumentQuality) -> "DocumentQualityResponse":
        return cls(**{field: getattr(quality, field) for field in cls.__dataclass_fields__})


@dataclass(frozen=True, slots=True)
class ExtractionRunResponse:
    id: UUID
    document_id: UUID
    processing_key: str
    extractor_name: str
    extractor_version: str
    configuration: dict[str, Any]
    status: ExtractionRunStatus
    started_at: datetime
    completed_at: datetime | None
    duration_ms: int | None
    pages_processed: int
    characters_extracted: int
    error_type: str | None
    error_message: str | None
    reused_from_run_id: UUID | None

    @classmethod
    def from_entity(cls, run: ExtractionRun) -> "ExtractionRunResponse":
        return cls(**{field: getattr(run, field) for field in cls.__dataclass_fields__})
