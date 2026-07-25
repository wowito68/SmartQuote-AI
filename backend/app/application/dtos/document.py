from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.domain.documents.entities import TenderDocument
from app.domain.documents.value_objects import DocumentStatus


@dataclass(frozen=True, slots=True)
class UploadDocumentFile:
    original_file_name: str
    declared_mime_type: str | None
    content: bytes


@dataclass(frozen=True, slots=True)
class UploadTenderDocumentRequest:
    uploaded_by_user_id: UUID
    files: tuple[UploadDocumentFile, ...]


@dataclass(frozen=True, slots=True)
class TenderDocumentResponse:
    id: UUID
    tender_id: UUID
    original_file_name: str
    mime_type: str
    file_size: int
    file_hash: str
    status: DocumentStatus
    uploaded_by_user_id: UUID
    uploaded_at: datetime
    updated_at: datetime

    @classmethod
    def from_entity(cls, document: TenderDocument) -> "TenderDocumentResponse":
        return cls(
            id=document.id,
            tender_id=document.tender_id,
            original_file_name=document.original_file_name,
            mime_type=document.mime_type,
            file_size=document.file_size,
            file_hash=document.file_hash.value,
            status=document.status,
            uploaded_by_user_id=document.uploaded_by_user_id,
            uploaded_at=document.created_at,
            updated_at=document.updated_at,
        )


@dataclass(frozen=True, slots=True)
class TenderDocumentListResponse:
    items: tuple[TenderDocumentResponse, ...]
    total: int


@dataclass(frozen=True, slots=True)
class DownloadTenderDocumentResponse:
    original_file_name: str
    mime_type: str
    content: bytes
