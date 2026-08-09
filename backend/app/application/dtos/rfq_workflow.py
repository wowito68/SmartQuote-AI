from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from app.domain.rfqs.value_objects import RfqStatus, TaskRecordStatus


@dataclass(frozen=True, slots=True)
class GenerateRfqCommand:
    tender_id: UUID
    supplier_id: UUID
    contact_id: UUID
    product_ids: tuple[UUID, ...]
    document_ids: tuple[UUID, ...]
    generated_by_user_id: UUID
    response_deadline: datetime
    observations: str | None = None
    requested_currency: str | None = None
    commercial_terms: str | None = None
    quote_validity: str | None = None
    response_instructions: str | None = None
    template_name: str = "supplier_rfq"
    template_version: str = "2.0.0"


@dataclass(frozen=True, slots=True)
class RfqVersionResponse:
    id: UUID
    rfq_id: UUID
    version: int
    changed_by_user_id: UUID
    status: RfqStatus
    contact_id: UUID | None
    subject: str
    body: str
    to_recipients: tuple[str, ...]
    cc_recipients: tuple[str, ...]
    bcc_recipients: tuple[str, ...]
    products: tuple[dict[str, Any], ...]
    attachment_snapshot: tuple[dict[str, Any], ...]
    change_reason: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class RfqVersionsResponse:
    rfq_id: UUID
    versions: tuple[RfqVersionResponse, ...]


@dataclass(frozen=True, slots=True)
class RfqTaskResponse:
    id: UUID
    rfq_id: UUID
    correlation_id: str
    task_name: str
    status: TaskRecordStatus
    attempt_count: int
    last_error: str | None
    queued_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
