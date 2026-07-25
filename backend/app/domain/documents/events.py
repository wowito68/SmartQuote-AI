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

    @property
    def aggregate_type(self) -> str:
        return "document"

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

    @property
    def aggregate_type(self) -> str:
        return "document"

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

    @property
    def aggregate_type(self) -> str:
        return "tender"

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


DocumentEvent = DocumentUploaded | DocumentDeleted | DuplicateDocumentDetected
