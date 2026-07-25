from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class DocumentUploaded:
    document_id: UUID
    tender_id: UUID
    uploaded_by_user_id: UUID
    file_hash: str
    event_id: UUID = field(default_factory=uuid4)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    aggregate_type = "document"

    @property
    def aggregate_id(self) -> UUID:
        return self.document_id

    @property
    def event_type(self) -> str:
        return type(self).__name__

    def payload(self) -> dict[str, Any]:
        return {
            "tender_id": str(self.tender_id),
            "uploaded_by_user_id": str(self.uploaded_by_user_id),
            "file_hash": self.file_hash,
        }


@dataclass(frozen=True, slots=True)
class DocumentDeleted:
    document_id: UUID
    tender_id: UUID
    deleted_by_user_id: UUID
    file_hash: str
    event_id: UUID = field(default_factory=uuid4)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    aggregate_type = "document"

    @property
    def aggregate_id(self) -> UUID:
        return self.document_id

    @property
    def event_type(self) -> str:
        return type(self).__name__

    def payload(self) -> dict[str, Any]:
        return {
            "tender_id": str(self.tender_id),
            "deleted_by_user_id": str(self.deleted_by_user_id),
            "file_hash": self.file_hash,
        }


@dataclass(frozen=True, slots=True)
class DuplicateDocumentDetected:
    tender_id: UUID
    uploaded_by_user_id: UUID
    file_hash: str
    original_file_name: str
    event_id: UUID = field(default_factory=uuid4)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    aggregate_type = "tender"

    @property
    def aggregate_id(self) -> UUID:
        return self.tender_id

    @property
    def event_type(self) -> str:
        return type(self).__name__

    def payload(self) -> dict[str, Any]:
        return {
            "uploaded_by_user_id": str(self.uploaded_by_user_id),
            "file_hash": self.file_hash,
            "original_file_name": self.original_file_name,
        }


@dataclass(frozen=True, slots=True)
class DocumentProcessingEvent:
    document_id: UUID
    event_name: str
    data: dict[str, Any] = field(default_factory=dict)
    event_id: UUID = field(default_factory=uuid4)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    aggregate_type = "document"

    @property
    def aggregate_id(self) -> UUID:
        return self.document_id

    @property
    def event_type(self) -> str:
        return self.event_name

    def payload(self) -> dict[str, Any]:
        return self.data


def document_queued(document_id: UUID, *, file_hash: str) -> DocumentProcessingEvent:
    return DocumentProcessingEvent(document_id, "DocumentQueued", {"file_hash": file_hash})


def document_processing_started(document_id: UUID) -> DocumentProcessingEvent:
    return DocumentProcessingEvent(document_id, "DocumentProcessingStarted")


def text_extraction_completed(
    document_id: UUID,
    *,
    extraction_run_id: UUID,
    extractor_name: str,
    extractor_version: str,
    pages_processed: int,
    characters_extracted: int,
    duration_ms: int,
    reused: bool = False,
) -> DocumentProcessingEvent:
    return DocumentProcessingEvent(
        document_id,
        "TextExtractionCompleted",
        {
            "extraction_run_id": str(extraction_run_id),
            "extractor_name": extractor_name,
            "extractor_version": extractor_version,
            "pages_processed": pages_processed,
            "characters_extracted": characters_extracted,
            "duration_ms": duration_ms,
            "reused": reused,
        },
    )


def quality_evaluation_completed(
    document_id: UUID,
    *,
    quality_id: UUID,
    decision: str,
    empty_page_percentage: float,
    text_density: float,
) -> DocumentProcessingEvent:
    return DocumentProcessingEvent(
        document_id,
        "QualityEvaluationCompleted",
        {
            "quality_id": str(quality_id),
            "decision": decision,
            "empty_page_percentage": empty_page_percentage,
            "text_density": text_density,
        },
    )


def document_ready_for_ai(document_id: UUID) -> DocumentProcessingEvent:
    return DocumentProcessingEvent(document_id, "DocumentReadyForAI")


def document_marked_for_ocr(
    document_id: UUID, *, requires_manual_review: bool
) -> DocumentProcessingEvent:
    return DocumentProcessingEvent(
        document_id,
        "DocumentMarkedForOCR",
        {"requires_manual_review": requires_manual_review},
    )


def document_processing_failed(
    document_id: UUID, *, error_type: str, error_message: str
) -> DocumentProcessingEvent:
    return DocumentProcessingEvent(
        document_id,
        "DocumentProcessingFailed",
        {"error_type": error_type, "error_message": error_message[:4000]},
    )


DocumentEvent = (
    DocumentUploaded
    | DocumentDeleted
    | DuplicateDocumentDetected
    | DocumentProcessingEvent
)
