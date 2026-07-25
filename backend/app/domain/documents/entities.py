from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import PurePosixPath
from uuid import UUID, uuid4

from app.domain.documents.exceptions import (
    DocumentAlreadyDeleted,
    InvalidDocumentFile,
    InvalidDocumentState,
)
from app.domain.documents.value_objects import DocumentStatus, FileHash
from app.domain.shared.exceptions import ValidationError

ORIGINAL_FILE_NAME_MAX_LENGTH = 255
PDF_MIME_TYPE = "application/pdf"

_ALLOWED_TRANSITIONS: dict[DocumentStatus, frozenset[DocumentStatus]] = {
    DocumentStatus.UPLOADED: frozenset(
        {DocumentStatus.QUEUED, DocumentStatus.REJECTED, DocumentStatus.DELETED}
    ),
    DocumentStatus.QUEUED: frozenset(
        {DocumentStatus.PROCESSING, DocumentStatus.FAILED, DocumentStatus.DELETED}
    ),
    DocumentStatus.PROCESSING: frozenset(
        {DocumentStatus.TEXT_EXTRACTED, DocumentStatus.FAILED, DocumentStatus.DELETED}
    ),
    DocumentStatus.TEXT_EXTRACTED: frozenset(
        {
            DocumentStatus.READY_FOR_AI,
            DocumentStatus.NEEDS_OCR,
            DocumentStatus.FAILED,
            DocumentStatus.DELETED,
        }
    ),
    DocumentStatus.READY_FOR_AI: frozenset({DocumentStatus.DELETED}),
    DocumentStatus.NEEDS_OCR: frozenset({DocumentStatus.QUEUED, DocumentStatus.DELETED}),
    DocumentStatus.FAILED: frozenset({DocumentStatus.QUEUED, DocumentStatus.DELETED}),
    DocumentStatus.REJECTED: frozenset({DocumentStatus.DELETED}),
    DocumentStatus.DELETED: frozenset(),
}


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def normalize_original_file_name(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValidationError("Document original file name is required.")
    if len(normalized) > ORIGINAL_FILE_NAME_MAX_LENGTH:
        raise ValidationError(
            f"Document original file name cannot exceed {ORIGINAL_FILE_NAME_MAX_LENGTH} characters."
        )
    if normalized in {".", ".."} or "/" in normalized or "\\" in normalized:
        raise InvalidDocumentFile("Document file name must not contain a path.")
    if any(ord(character) < 32 for character in normalized):
        raise InvalidDocumentFile("Document file name contains control characters.")
    if not normalized.lower().endswith(".pdf"):
        raise InvalidDocumentFile("Only files with a .pdf extension are accepted.")
    return normalized


def validate_storage_key(value: str) -> str:
    normalized = value.strip()
    path = PurePosixPath(normalized)
    if not normalized or path.is_absolute() or ".." in path.parts:
        raise ValidationError("Document storage key must be a safe relative path.")
    if "\\" in normalized or normalized.startswith("."):
        raise ValidationError("Document storage key must use a safe POSIX path.")
    return normalized


@dataclass(slots=True)
class TenderDocument:
    tender_id: UUID
    original_file_name: str
    storage_key: str
    mime_type: str
    file_size: int
    file_hash: FileHash
    uploaded_by_user_id: UUID
    status: DocumentStatus = DocumentStatus.UPLOADED
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    deleted_at: datetime | None = None
    queued_at: datetime | None = None
    processing_started_at: datetime | None = None
    processed_at: datetime | None = None
    requires_ocr: bool = False
    last_processing_error: str | None = None

    def __post_init__(self) -> None:
        self.original_file_name = normalize_original_file_name(self.original_file_name)
        self.storage_key = validate_storage_key(self.storage_key)
        self.mime_type = self.mime_type.strip().lower()
        if self.mime_type != PDF_MIME_TYPE:
            raise InvalidDocumentFile("Only application/pdf documents are accepted.")
        if self.file_size <= 0:
            raise ValidationError("Document file size must be greater than zero.")
        self.created_at = _as_utc(self.created_at)
        self.updated_at = _as_utc(self.updated_at)
        self.deleted_at = _as_utc(self.deleted_at) if self.deleted_at else None
        self.queued_at = _as_utc(self.queued_at) if self.queued_at else None
        self.processing_started_at = (
            _as_utc(self.processing_started_at) if self.processing_started_at else None
        )
        self.processed_at = _as_utc(self.processed_at) if self.processed_at else None
        if self.status is DocumentStatus.DELETED and self.deleted_at is None:
            self.deleted_at = self.updated_at
        if self.status is not DocumentStatus.DELETED and self.deleted_at is not None:
            raise ValidationError("Only deleted documents can have deleted_at set.")
        if self.status is DocumentStatus.NEEDS_OCR:
            self.requires_ocr = True

    @property
    def is_deleted(self) -> bool:
        return self.status is DocumentStatus.DELETED

    def _transition(self, target: DocumentStatus, *, now: datetime | None = None) -> None:
        if target is self.status:
            return
        if target not in _ALLOWED_TRANSITIONS[self.status]:
            raise InvalidDocumentState(
                f"Document cannot transition from {self.status.value} to {target.value}."
            )
        self.status = target
        self.updated_at = _as_utc(now or datetime.now(UTC))

    def mark_queued(self) -> None:
        if self.status is DocumentStatus.QUEUED:
            return
        self._transition(DocumentStatus.QUEUED)
        self.queued_at = self.updated_at
        self.last_processing_error = None
        self.requires_ocr = False

    def start_processing(self) -> None:
        if self.status is DocumentStatus.PROCESSING:
            return
        self._transition(DocumentStatus.PROCESSING)
        self.processing_started_at = self.updated_at
        self.last_processing_error = None

    def mark_text_extracted(self) -> None:
        if self.status is DocumentStatus.TEXT_EXTRACTED:
            return
        self._transition(DocumentStatus.TEXT_EXTRACTED)

    def mark_ready_for_ai(self) -> None:
        if self.status is DocumentStatus.READY_FOR_AI:
            return
        self._transition(DocumentStatus.READY_FOR_AI)
        self.processed_at = self.updated_at
        self.requires_ocr = False

    def mark_needs_ocr(self) -> None:
        if self.status is DocumentStatus.NEEDS_OCR:
            return
        self._transition(DocumentStatus.NEEDS_OCR)
        self.processed_at = self.updated_at
        self.requires_ocr = True

    def mark_failed(self, error: str) -> None:
        normalized = error.strip() or "Document processing failed."
        if self.status is DocumentStatus.FAILED:
            self.last_processing_error = normalized[:2000]
            self.updated_at = datetime.now(UTC)
            return
        self._transition(DocumentStatus.FAILED)
        self.processed_at = self.updated_at
        self.last_processing_error = normalized[:2000]

    def mark_deleted(self) -> None:
        if self.is_deleted:
            raise DocumentAlreadyDeleted("Document is already deleted.")
        self._transition(DocumentStatus.DELETED)
        self.deleted_at = self.updated_at

    def mark_rejected(self) -> None:
        if self.is_deleted:
            raise DocumentAlreadyDeleted("Deleted documents cannot be rejected.")
        self._transition(DocumentStatus.REJECTED)
