from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from app.domain.rfqs.value_objects import EmailMessageStatus, OutboundLogResult, RfqStatus


@dataclass(frozen=True, slots=True)
class GenerateRfqsCommand:
    tender_id: UUID
    generated_by_user_id: UUID
    response_deadline: datetime
    observations: str | None = None
    template_name: str = "supplier_rfq"
    template_version: str = "1.0.0"
    document_ids: tuple[UUID, ...] | None = None


@dataclass(frozen=True, slots=True)
class UpdateRfqCommand:
    changed_by_user_id: UUID
    subject: str | None = None
    body: str | None = None
    to_recipients: tuple[str, ...] | None = None
    cc_recipients: tuple[str, ...] | None = None
    bcc_recipients: tuple[str, ...] | None = None
    response_deadline: datetime | None = None
    observations: str | None = None
    contact_name: str | None = None
    document_ids: tuple[UUID, ...] | None = None


@dataclass(frozen=True, slots=True)
class RfqAttachmentResponse:
    id: UUID
    document_id: UUID
    original_file_name: str
    file_hash: str
    file_size: int
    mime_type: str


@dataclass(frozen=True, slots=True)
class RfqResponse:
    id: UUID
    tender_id: UUID
    tender_supplier_id: UUID
    supplier_id: UUID
    contact_id: UUID | None
    catalog_snapshot_id: UUID
    status: RfqStatus
    version: int
    generation_duration_ms: int
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
    attachments: tuple[RfqAttachmentResponse, ...]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class RfqGenerationResponse:
    tender_id: UUID
    generated: tuple[RfqResponse, ...]
    reused: tuple[RfqResponse, ...]
    suppliers_without_email: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class RfqMetricsResponse:
    total: int
    pending_review: int
    approved: int
    queued: int
    sent: int
    failed: int
    cancelled: int
    success_percentage: float
    average_attachment_size_bytes: float
    average_send_duration_ms: float
    retries: int


@dataclass(frozen=True, slots=True)
class TenderRfqsResponse:
    tender_id: UUID
    rfqs: tuple[RfqResponse, ...]
    metrics: RfqMetricsResponse


@dataclass(frozen=True, slots=True)
class OutboundLogResponse:
    id: UUID
    event_type: str
    result: OutboundLogResult
    provider_name: str
    details: dict[str, Any]
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class EmailMessageResponse:
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
    failed_at: datetime | None
    duration_ms: int | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class RfqMessagesResponse:
    rfq_id: UUID
    messages: tuple[EmailMessageResponse, ...]
    logs: tuple[OutboundLogResponse, ...]


@dataclass(frozen=True, slots=True)
class CompanyProfile:
    name: str
    contact_name: str
    email: str
    phone: str | None = None
