from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.api.quote_schemas import (
    QuoteEvidenceResponseSchema,
    QuoteExtractionRunResponseSchema,
    QuoteItemResponseSchema,
    QuoteProcessingStatusResponseSchema,
)
from app.domain.quotes.value_objects import QuoteStatus


class QuoteAnalyzeRequestSchema(BaseModel):
    requested_by_user_id: UUID


class ExtractionArtifactResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    extraction_run_id: UUID
    schema_version: str
    structured_output: dict[str, Any]
    created_at: datetime


class QuoteAnalysisResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    quote_id: UUID
    quote_status: QuoteStatus
    processing: QuoteProcessingStatusResponseSchema
    latest_run: QuoteExtractionRunResponseSchema | None
    artifact: ExtractionArtifactResponseSchema | None
    items: tuple[QuoteItemResponseSchema, ...]
    evidence: tuple[QuoteEvidenceResponseSchema, ...]
    requires_review: bool
    last_error: str | None
