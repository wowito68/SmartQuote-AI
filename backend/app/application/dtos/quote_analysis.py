from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from app.application.dtos.quotes import (
    QuoteEvidenceResponse,
    QuoteExtractionRunResponse,
    QuoteItemResponse,
    QuoteProcessingStatusResponse,
)
from app.domain.quotes.value_objects import QuoteStatus


@dataclass(frozen=True, slots=True)
class ExtractionArtifactResponse:
    id: UUID
    extraction_run_id: UUID
    schema_version: str
    structured_output: dict[str, Any]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class QuoteAnalysisResponse:
    quote_id: UUID
    quote_status: QuoteStatus
    processing: QuoteProcessingStatusResponse
    latest_run: QuoteExtractionRunResponse | None
    artifact: ExtractionArtifactResponse | None
    items: tuple[QuoteItemResponse, ...]
    evidence: tuple[QuoteEvidenceResponse, ...]
    requires_review: bool
    last_error: str | None
