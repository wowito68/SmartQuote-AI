from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.domain.shared.exceptions import InvalidStateTransitionError, ValidationError
from app.domain.shared.value_objects import FileHash
from app.domain.tenders.exceptions import InvalidDeadline, InvalidTenderState, TenderAlreadyArchived
from app.domain.tenders.value_objects import DocumentStatus, TenderStatus

TITLE_MAX_LENGTH = 255
DESCRIPTION_MAX_LENGTH = 5000

_ALLOWED_STATUS_TRANSITIONS: dict[TenderStatus, frozenset[TenderStatus]] = {
    TenderStatus.DRAFT: frozenset({TenderStatus.DOCUMENTS_PENDING, TenderStatus.CANCELLED}),
    TenderStatus.DOCUMENTS_PENDING: frozenset(
        {TenderStatus.DOCUMENTS_PROCESSING, TenderStatus.CANCELLED}
    ),
    TenderStatus.DOCUMENTS_PROCESSING: frozenset(
        {TenderStatus.CATALOG_REVIEW, TenderStatus.CANCELLED}
    ),
    TenderStatus.CATALOG_REVIEW: frozenset({TenderStatus.CLOSED, TenderStatus.CANCELLED}),
    TenderStatus.CANCELLED: frozenset(),
    TenderStatus.CLOSED: frozenset(),
}


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _normalize_title(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValidationError("Tender title is required.")
    if len(normalized) > TITLE_MAX_LENGTH:
        raise ValidationError(f"Tender title cannot exceed {TITLE_MAX_LENGTH} characters.")
    return normalized


def _normalize_description(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized) > DESCRIPTION_MAX_LENGTH:
        raise ValidationError(
            f"Tender description cannot exceed {DESCRIPTION_MAX_LENGTH} characters."
        )
    return normalized


@dataclass(slots=True)
class TenderDocument:
    tender_id: UUID
    file_name: str
    file_path: str
    mime_type: str
    file_size: int
    file_hash: FileHash
    uploaded_by_user_id: UUID
    document_type: str = "tender_pdf"
    processing_status: DocumentStatus = DocumentStatus.UPLOADED
    requires_ocr: bool = False
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.file_name.strip():
            raise ValidationError("Document file name is required.")
        if not self.file_path.strip():
            raise ValidationError("Document file path is required.")
        if not self.mime_type.strip():
            raise ValidationError("Document MIME type is required.")
        if self.file_size <= 0:
            raise ValidationError("Document file size must be greater than zero.")
        if not self.document_type.strip():
            raise ValidationError("Document type is required.")
        self.file_name = self.file_name.strip()
        self.file_path = self.file_path.strip()
        self.mime_type = self.mime_type.strip().lower()
        self.document_type = self.document_type.strip()
        self.created_at = _as_utc(self.created_at)
        self.updated_at = _as_utc(self.updated_at)

    def mark_valid(self) -> None:
        if self.processing_status not in {DocumentStatus.UPLOADED, DocumentStatus.VALIDATING}:
            raise InvalidStateTransitionError("Only uploaded documents can be marked valid.")
        self.processing_status = DocumentStatus.VALID
        self.updated_at = datetime.now(UTC)

    def mark_rejected(self) -> None:
        self.processing_status = DocumentStatus.REJECTED
        self.updated_at = datetime.now(UTC)


@dataclass(slots=True)
class Tender:
    title: str
    created_by_user_id: UUID
    description: str | None = None
    status: TenderStatus = TenderStatus.DRAFT
    deadline: datetime | None = None
    documents: list[TenderDocument] = field(default_factory=list)
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    deleted_at: datetime | None = None

    def __post_init__(self) -> None:
        self.created_at = _as_utc(self.created_at)
        self.updated_at = _as_utc(self.updated_at)
        self.deleted_at = _as_utc(self.deleted_at) if self.deleted_at else None
        self.title = _normalize_title(self.title)
        self.description = _normalize_description(self.description)
        self.deadline = self._validate_deadline(self.deadline)

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def _ensure_active(self) -> None:
        if self.is_deleted:
            raise TenderAlreadyArchived("Archived tenders cannot be modified.")

    def _validate_deadline(self, deadline: datetime | None) -> datetime | None:
        if deadline is None:
            return None
        normalized = _as_utc(deadline)
        if normalized < self.created_at:
            raise InvalidDeadline("Tender deadline cannot be earlier than its creation date.")
        return normalized

    def add_document(self, document: TenderDocument) -> None:
        self._ensure_active()
        if document.tender_id != self.id:
            raise ValidationError("Document belongs to a different tender.")
        self.documents.append(document)
        if self.status == TenderStatus.DRAFT:
            self.change_status(TenderStatus.DOCUMENTS_PENDING)
        else:
            self.updated_at = datetime.now(UTC)

    def change_status(self, status: TenderStatus) -> None:
        self._ensure_active()
        if status == self.status:
            return
        allowed = _ALLOWED_STATUS_TRANSITIONS[self.status]
        if status not in allowed:
            raise InvalidTenderState(
                f"Cannot transition tender from '{self.status.value}' to '{status.value}'."
            )
        self.status = status
        self.updated_at = datetime.now(UTC)

    def replace_details(
        self,
        *,
        title: str,
        description: str | None,
        deadline: datetime | None,
        status: TenderStatus,
    ) -> tuple[str, ...]:
        self._ensure_active()
        normalized_title = _normalize_title(title)
        normalized_description = _normalize_description(description)
        normalized_deadline = self._validate_deadline(deadline)

        changed_fields: list[str] = []
        if normalized_title != self.title:
            self.title = normalized_title
            changed_fields.append("title")
        if normalized_description != self.description:
            self.description = normalized_description
            changed_fields.append("description")
        if normalized_deadline != self.deadline:
            self.deadline = normalized_deadline
            changed_fields.append("deadline")
        if status != self.status:
            self.change_status(status)
            changed_fields.append("status")

        if changed_fields:
            self.updated_at = datetime.now(UTC)
        return tuple(changed_fields)

    def update_details(
        self,
        *,
        title: str | None = None,
        description: str | None = None,
        deadline: datetime | None = None,
    ) -> None:
        """Compatibility helper retained from Iteration 2."""
        self._ensure_active()
        if title is not None:
            self.title = _normalize_title(title)
        if description is not None:
            self.description = _normalize_description(description)
        if deadline is not None:
            self.deadline = self._validate_deadline(deadline)
        self.updated_at = datetime.now(UTC)

    def archive(self) -> None:
        if self.is_deleted:
            raise TenderAlreadyArchived("Tender is already archived.")
        self.deleted_at = datetime.now(UTC)
        self.updated_at = self.deleted_at

    def soft_delete(self) -> None:
        self.archive()
