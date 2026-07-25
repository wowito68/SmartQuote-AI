from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import PurePosixPath
from uuid import UUID, uuid4

from app.domain.documents.exceptions import DocumentAlreadyDeleted, InvalidDocumentFile
from app.domain.documents.value_objects import DocumentStatus, FileHash
from app.domain.shared.exceptions import ValidationError

ORIGINAL_FILE_NAME_MAX_LENGTH = 255
PDF_MIME_TYPE = "application/pdf"


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
        if self.status is DocumentStatus.DELETED and self.deleted_at is None:
            self.deleted_at = self.updated_at
        if self.status is not DocumentStatus.DELETED and self.deleted_at is not None:
            raise ValidationError("Only deleted documents can have deleted_at set.")

    @property
    def is_deleted(self) -> bool:
        return self.status is DocumentStatus.DELETED

    def mark_deleted(self) -> None:
        if self.is_deleted:
            raise DocumentAlreadyDeleted("Document is already deleted.")
        now = datetime.now(UTC)
        self.status = DocumentStatus.DELETED
        self.deleted_at = now
        self.updated_at = now

    def mark_rejected(self) -> None:
        if self.is_deleted:
            raise DocumentAlreadyDeleted("Deleted documents cannot be rejected.")
        self.status = DocumentStatus.REJECTED
        self.updated_at = datetime.now(UTC)
