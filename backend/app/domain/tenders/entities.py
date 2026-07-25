from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.domain.shared.exceptions import InvalidStateTransitionError, ValidationError
from app.domain.shared.value_objects import FileHash
from app.domain.tenders.value_objects import DocumentStatus, TenderStatus


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
        if not self.title.strip():
            raise ValidationError("Tender title is required.")
        self.title = self.title.strip()
        self.description = self.description.strip() if self.description else None

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def add_document(self, document: TenderDocument) -> None:
        if self.is_deleted:
            raise InvalidStateTransitionError("Cannot add documents to a deleted tender.")
        if document.tender_id != self.id:
            raise ValidationError("Document belongs to a different tender.")
        self.documents.append(document)
        if self.status == TenderStatus.DRAFT:
            self.status = TenderStatus.DOCUMENTS_PENDING
        self.updated_at = datetime.now(UTC)

    def update_details(
        self,
        *,
        title: str | None = None,
        description: str | None = None,
        deadline: datetime | None = None,
    ) -> None:
        if self.is_deleted:
            raise InvalidStateTransitionError("Cannot update a deleted tender.")
        if title is not None:
            if not title.strip():
                raise ValidationError("Tender title is required.")
            self.title = title.strip()
        if description is not None:
            self.description = description.strip() or None
        if deadline is not None:
            self.deadline = deadline
        self.updated_at = datetime.now(UTC)

    def soft_delete(self) -> None:
        if self.is_deleted:
            return
        self.deleted_at = datetime.now(UTC)
        self.updated_at = self.deleted_at

