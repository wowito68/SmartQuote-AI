from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.rfqs.value_objects import EmailMessageStatus, OutboundLogResult, RfqStatus


class GenerateRfqsRequestSchema(BaseModel):
    generated_by_user_id: UUID
    response_deadline: datetime
    observations: str | None = Field(default=None, max_length=5000)
    template_name: str = Field(default="supplier_rfq", min_length=1, max_length=100)
    template_version: str = Field(default="1.0.0", min_length=1, max_length=50)
    document_ids: tuple[UUID, ...] | None = None

    @field_validator("response_deadline")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("RFQ response deadline must include a timezone.")
        return value


class UpdateRfqRequestSchema(BaseModel):
    changed_by_user_id: UUID
    subject: str | None = Field(default=None, min_length=1, max_length=998)
    body: str | None = Field(default=None, min_length=1, max_length=200_000)
    to_recipients: tuple[str, ...] | None = None
    cc_recipients: tuple[str, ...] | None = None
    bcc_recipients: tuple[str, ...] | None = None
    response_deadline: datetime | None = None
    observations: str | None = Field(default=None, max_length=5000)
    contact_name: str | None = Field(default=None, max_length=255)
    document_ids: tuple[UUID, ...] | None = None

    @field_validator("response_deadline")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("RFQ response deadline must include a timezone.")
        return value


class RfqApprovalRequestSchema(BaseModel):
    approved_by_user_id: UUID


class RfqCancellationRequestSchema(BaseModel):
    cancelled_by_user_id: UUID
    reason: str | None = Field(default=None, max_length=2000)


class RfqSendRequestSchema(BaseModel):
    requested_by_user_id: UUID


class RfqAttachmentResponseSchema(BaseModel):
    id: UUID
    document_id: UUID
    original_file_name: str
    file_hash: str
    file_size: int = Field(gt=0)
    mime_type: str

    model_config = ConfigDict(from_attributes=True)


class RfqResponseSchema(BaseModel):
    id: UUID
    tender_id: UUID
    tender_supplier_id: UUID
    supplier_id: UUID
    catalog_snapshot_id: UUID
    status: RfqStatus
    version: int = Field(ge=1)
    generation_duration_ms: int = Field(ge=0)
    template_name: str
    template_version: str
    subject: str
    body: str
    products: tuple[dict[str, Any], ...]
    to_recipients: tuple[str, ...]
    cc_recipients: tuple[str, ...]
    bcc_recipients: tuple[str, ...]
    contact_name: str | None
    response_deadline: datetime
    observations: str | None
    generated_by_user_id: UUID
    approved_by_user_id: UUID | None
    approved_at: datetime | None
    send_requested_by_user_id: UUID | None
    queued_at: datetime | None
    sending_started_at: datetime | None
    sent_at: datetime | None
    delivered_at: datetime | None
    cancelled_by_user_id: UUID | None
    cancelled_at: datetime | None
    cancellation_reason: str | None
    last_error: str | None
    send_idempotency_key: str | None
    attachments: tuple[RfqAttachmentResponseSchema, ...]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RfqGenerationResponseSchema(BaseModel):
    tender_id: UUID
    generated: tuple[RfqResponseSchema, ...]
    reused: tuple[RfqResponseSchema, ...]
    suppliers_without_email: tuple[UUID, ...]

    model_config = ConfigDict(from_attributes=True)


class RfqMetricsResponseSchema(BaseModel):
    total: int = Field(ge=0)
    pending_review: int = Field(ge=0)
    approved: int = Field(ge=0)
    queued: int = Field(ge=0)
    sent: int = Field(ge=0)
    failed: int = Field(ge=0)
    cancelled: int = Field(ge=0)
    success_percentage: float = Field(ge=0, le=100)
    average_attachment_size_bytes: float = Field(ge=0)
    average_send_duration_ms: float = Field(ge=0)
    retries: int = Field(ge=0)

    model_config = ConfigDict(from_attributes=True)


class TenderRfqsResponseSchema(BaseModel):
    tender_id: UUID
    rfqs: tuple[RfqResponseSchema, ...]
    metrics: RfqMetricsResponseSchema

    model_config = ConfigDict(from_attributes=True)


class EmailMessageResponseSchema(BaseModel):
    id: UUID
    rfq_id: UUID
    rfq_version: int
    attempt_number: int
    idempotency_key: str
    provider_name: str
    from_address: str
    to_recipients: tuple[str, ...]
    cc_recipients: tuple[str, ...]
    bcc_recipients: tuple[str, ...]
    subject: str
    status: EmailMessageStatus
    attachment_snapshot: tuple[dict[str, Any], ...]
    external_message_id: str | None
    error_type: str | None
    error_message: str | None
    started_at: datetime | None
    sent_at: datetime | None
    duration_ms: int | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OutboundLogResponseSchema(BaseModel):
    id: UUID
    event_type: str
    result: OutboundLogResult
    provider_name: str
    details: dict[str, Any]
    occurred_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RfqMessagesResponseSchema(BaseModel):
    rfq_id: UUID
    messages: tuple[EmailMessageResponseSchema, ...]
    logs: tuple[OutboundLogResponseSchema, ...]

    model_config = ConfigDict(from_attributes=True)
