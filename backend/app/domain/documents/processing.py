from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from app.domain.documents.value_objects import (
    DocumentQualityDecision,
    DocumentQualityLevel,
    ExtractionRunStatus,
)
from app.domain.shared.exceptions import ValidationError


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class DocumentPage:
    document_id: UUID
    extraction_run_id: UUID
    page_number: int
    text: str
    width: float
    height: float
    duration_ms: int
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=_now)

    def __post_init__(self) -> None:
        if self.page_number < 1:
            raise ValidationError("Document page numbers start at one.")
        if self.width <= 0 or self.height <= 0:
            raise ValidationError("Document page dimensions must be positive.")
        if self.duration_ms < 0:
            raise ValidationError("Document page duration cannot be negative.")

    @property
    def character_count(self) -> int:
        return len(self.text.strip())

    @property
    def word_count(self) -> int:
        return len(self.text.split())

    @property
    def is_empty(self) -> bool:
        return self.character_count < 5

    @property
    def text_density(self) -> float:
        area_square_inches = (self.width * self.height) / (72.0 * 72.0)
        return self.character_count / max(area_square_inches, 1.0)


@dataclass(slots=True)
class ExtractionRun:
    document_id: UUID
    processing_key: str
    extractor_name: str
    extractor_version: str
    configuration: dict[str, Any]
    extraction_type: str = "text"
    status: ExtractionRunStatus = ExtractionRunStatus.RUNNING
    id: UUID = field(default_factory=uuid4)
    started_at: datetime = field(default_factory=_now)
    completed_at: datetime | None = None
    duration_ms: int | None = None
    pages_processed: int = 0
    characters_extracted: int = 0
    error_type: str | None = None
    error_message: str | None = None
    reused_from_run_id: UUID | None = None
    created_at: datetime = field(default_factory=_now)

    def __post_init__(self) -> None:
        if len(self.processing_key) != 64:
            raise ValidationError("Extraction processing key must be a SHA-256 digest.")
        self.extraction_type = self.extraction_type.strip().lower()
        if not self.extraction_type:
            raise ValidationError("Extraction type is required.")
        if not self.extractor_name.strip() or not self.extractor_version.strip():
            raise ValidationError("Extractor name and version are required.")

    def restart(self) -> None:
        self.status = ExtractionRunStatus.RUNNING
        self.started_at = _now()
        self.completed_at = None
        self.duration_ms = None
        self.pages_processed = 0
        self.characters_extracted = 0
        self.error_type = None
        self.error_message = None
        self.reused_from_run_id = None

    def complete(self, pages: list[DocumentPage], duration_ms: int) -> None:
        self.status = ExtractionRunStatus.COMPLETED
        self.completed_at = _now()
        self.duration_ms = max(duration_ms, 0)
        self.pages_processed = len(pages)
        self.characters_extracted = sum(page.character_count for page in pages)
        self.error_type = None
        self.error_message = None

    def fail(self, error: Exception) -> None:
        self.status = ExtractionRunStatus.FAILED
        self.completed_at = _now()
        elapsed_ms = int((self.completed_at - self.started_at).total_seconds() * 1000)
        self.duration_ms = max(elapsed_ms, 0)
        self.error_type = type(error).__name__
        self.error_message = str(error)[:4000]

    def mark_reused(self, source_run_id: UUID) -> None:
        self.status = ExtractionRunStatus.REUSED
        self.completed_at = _now()
        self.duration_ms = 0
        self.reused_from_run_id = source_run_id


@dataclass(frozen=True, slots=True)
class DocumentQuality:
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
    id: UUID = field(default_factory=uuid4)
    evaluated_at: datetime = field(default_factory=_now)

    def __post_init__(self) -> None:
        if self.pages_processed < 0 or self.empty_pages < 0 or self.characters_extracted < 0:
            raise ValidationError("Document quality counters cannot be negative.")
        if self.empty_pages > self.pages_processed:
            raise ValidationError("Empty pages cannot exceed processed pages.")
        if not 0.0 <= self.empty_page_percentage <= 100.0:
            raise ValidationError("Empty-page percentage must be between zero and one hundred.")
        if self.text_density < 0:
            raise ValidationError("Text density cannot be negative.")
