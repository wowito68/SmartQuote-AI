from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.documents.value_objects import (
    DocumentQualityDecision,
    DocumentQualityLevel,
    DocumentStatus,
    ExtractionRunStatus,
)


class DocumentStatusResponseSchema(BaseModel):
    document_id: UUID
    status: DocumentStatus
    requires_ocr: bool
    last_processing_error: str | None
    queued_at: datetime | None
    processing_started_at: datetime | None
    processed_at: datetime | None
    model_config = ConfigDict(from_attributes=True)


class DocumentPageResponseSchema(BaseModel):
    id: UUID
    document_id: UUID
    extraction_run_id: UUID
    page_number: int = Field(gt=0)
    text: str
    character_count: int = Field(ge=0)
    word_count: int = Field(ge=0)
    is_empty: bool
    text_density: float = Field(ge=0)
    duration_ms: int = Field(ge=0)
    model_config = ConfigDict(from_attributes=True)


class DocumentPageListResponseSchema(BaseModel):
    items: list[DocumentPageResponseSchema]
    total: int = Field(ge=0)


class DocumentQualityResponseSchema(BaseModel):
    id: UUID
    document_id: UUID
    extraction_run_id: UUID
    pages_processed: int = Field(ge=0)
    empty_pages: int = Field(ge=0)
    characters_extracted: int = Field(ge=0)
    empty_page_percentage: float = Field(ge=0, le=100)
    text_density: float = Field(ge=0)
    quality_level: DocumentQualityLevel
    decision: DocumentQualityDecision
    requires_manual_review: bool
    evaluated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class ExtractionRunResponseSchema(BaseModel):
    id: UUID
    document_id: UUID
    processing_key: str = Field(min_length=64, max_length=64)
    extractor_name: str
    extractor_version: str
    configuration: dict[str, Any]
    status: ExtractionRunStatus
    started_at: datetime
    completed_at: datetime | None
    duration_ms: int | None
    pages_processed: int = Field(ge=0)
    characters_extracted: int = Field(ge=0)
    error_type: str | None
    error_message: str | None
    reused_from_run_id: UUID | None
    model_config = ConfigDict(from_attributes=True)
