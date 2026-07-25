from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.documents.value_objects import DocumentStatus


class TenderDocumentResponseSchema(BaseModel):
    id: UUID
    tender_id: UUID
    original_file_name: str
    mime_type: str
    file_size: int = Field(gt=0)
    file_hash: str = Field(min_length=64, max_length=64)
    status: DocumentStatus
    uploaded_by_user_id: UUID
    uploaded_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TenderDocumentListResponseSchema(BaseModel):
    items: list[TenderDocumentResponseSchema]
    total: int = Field(ge=0)
