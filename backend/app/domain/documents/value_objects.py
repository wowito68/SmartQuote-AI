from enum import StrEnum

from app.domain.shared.value_objects import FileHash


class DocumentStatus(StrEnum):
    UPLOADED = "uploaded"
    QUEUED = "queued"
    PROCESSING = "processing"
    TEXT_EXTRACTED = "text_extracted"
    READY_FOR_AI = "ready_for_ai"
    NEEDS_OCR = "needs_ocr"
    FAILED = "failed"
    DELETED = "deleted"
    REJECTED = "rejected"


class ExtractionRunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    REUSED = "reused"


class DocumentQualityLevel(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class DocumentQualityDecision(StrEnum):
    READY_FOR_AI = "ready_for_ai"
    NEEDS_OCR = "needs_ocr"
    MANUAL_REVIEW = "manual_review"


__all__ = [
    "DocumentQualityDecision",
    "DocumentQualityLevel",
    "DocumentStatus",
    "ExtractionRunStatus",
    "FileHash",
]
