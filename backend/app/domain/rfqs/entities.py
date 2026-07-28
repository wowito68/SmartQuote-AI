import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from app.domain.rfqs.exceptions import AttachmentValidationError, InvalidRfqState
from app.domain.rfqs.value_objects import (
    EmailAddress,
    EmailMessageStatus,
    OutboundLogResult,
    RfqStatus,
)
from app.domain.shared.exceptions import ValidationError


def _now() -> datetime:
    return datetime.now(UTC)


def _clean(value: str | None, *, limit: int | None = None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.split())
    if not cleaned:
        return None
    if limit and len(cleaned) > limit:
        raise ValidationError(f"Value cannot exceed {limit} characters.")
    return cleaned


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _normalize_addresses(values: tuple[str, ...]) -> tuple[str, ...]:
    normalized = tuple(dict.fromkeys(EmailAddress(value).value for value in values))
    if len(normalized) > 50:
        raise ValidationError("An email message cannot contain more than 50 recipients.")
    return normalized


_RFQ_TRANSITIONS: dict[RfqStatus, frozenset[RfqStatus]] = {
    RfqStatus.DRAFT: frozenset({RfqStatus.PENDING_REVIEW, RfqStatus.CANCELLED}),
    RfqStatus.PENDING_REVIEW: frozenset({RfqStatus.APPROVED, RfqStatus.CANCELLED}),
    RfqStatus.APPROVED: frozenset({RfqStatus.QUEUED, RfqStatus.CANCELLED}),
    RfqStatus.QUEUED: frozenset(
        {RfqStatus.SENDING, RfqStatus.FAILED, RfqStatus.CANCELLED}
    ),
    RfqStatus.SENDING: frozenset({RfqStatus.SENT, RfqStatus.FAILED}),
    RfqStatus.SENT: frozenset({RfqStatus.DELIVERED}),
    RfqStatus.DELIVERED: frozenset(),
    RfqStatus.FAILED: frozenset({RfqStatus.QUEUED, RfqStatus.CANCELLED}),
    RfqStatus.CANCELLED: frozenset(),
}


@dataclass(frozen=True, slots=True)
class EmailTemplate:
    name: str
    version: str
    subject_template: str
    body_template: str
    content_type: str = "text/plain"

    def __post_init__(self) -> None:
        if not _clean(self.name, limit=100):
            raise ValidationError("Email template name is required.")
        if not _clean(self.version, limit=50):
            raise ValidationError("Email template version is required.")
        if not self.subject_template.strip() or not self.body_template.strip():
            raise ValidationError("Email template subject and body are required.")
        if self.content_type not in {"text/plain", "text/html"}:
            raise ValidationError("Unsupported email template content type.")


@dataclass(frozen=True, slots=True)
class EmailAttachment:
    rfq_id: UUID
    document_id: UUID
    original_file_name: str
    file_hash: str
    file_size: int
    mime_type: str
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=_now)

    def __post_init__(self) -> None:
        name = self.original_file_name.strip()
        if not name or len(name) > 255 or "/" in name or "\\" in name:
            raise AttachmentValidationError("Attachment file name is invalid.")
        digest = self.file_hash.strip().lower()
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise AttachmentValidationError("Attachment SHA-256 hash is invalid.")
        if self.file_size <= 0:
            raise AttachmentValidationError("Attachment size must be greater than zero.")
        mime = self.mime_type.strip().lower()
        if mime != "application/pdf":
            raise AttachmentValidationError("Only PDF attachments are supported.")
        object.__setattr__(self, "original_file_name", name)
        object.__setattr__(self, "file_hash", digest)
        object.__setattr__(self, "mime_type", mime)
        object.__setattr__(self, "created_at", _as_utc(self.created_at))

    def snapshot(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "document_id": str(self.document_id),
            "name": self.original_file_name,
            "hash": self.file_hash,
            "size": self.file_size,
            "mime_type": self.mime_type,
        }


@dataclass(slots=True)
class RfqRequest:
    tender_id: UUID
    tender_supplier_id: UUID
    supplier_id: UUID
    catalog_snapshot_id: UUID
    generated_by_user_id: UUID
    response_deadline: datetime
    template_name: str
    template_version: str
    subject: str
    body: str
    products: tuple[dict[str, Any], ...]
    generation_key: str
    generation_duration_ms: int = 0
    to_recipients: tuple[str, ...] = ()
    cc_recipients: tuple[str, ...] = ()
    bcc_recipients: tuple[str, ...] = ()
    contact_name: str | None = None
    observations: str | None = None
    status: RfqStatus = RfqStatus.DRAFT
    version: int = 1
    id: UUID = field(default_factory=uuid4)
    approved_by_user_id: UUID | None = None
    approved_at: datetime | None = None
    send_requested_by_user_id: UUID | None = None
    queued_at: datetime | None = None
    sending_started_at: datetime | None = None
    sent_at: datetime | None = None
    delivered_at: datetime | None = None
    cancelled_by_user_id: UUID | None = None
    cancelled_at: datetime | None = None
    cancellation_reason: str | None = None
    last_error: str | None = None
    send_idempotency_key: str | None = None
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)

    def __post_init__(self) -> None:
        self.created_at = _as_utc(self.created_at)
        self.updated_at = _as_utc(self.updated_at)
        self.response_deadline = _as_utc(self.response_deadline)
        if self.response_deadline <= self.created_at:
            raise ValidationError("RFQ response deadline must be after creation time.")
        self.template_name = _clean(self.template_name, limit=100) or ""
        self.template_version = _clean(self.template_version, limit=50) or ""
        self.subject = self.subject.strip()
        self.body = self.body.strip()
        if not self.template_name or not self.template_version:
            raise ValidationError("RFQ template name and version are required.")
        if not self.subject or len(self.subject) > 998:
            raise ValidationError("RFQ subject is required and must not exceed 998 characters.")
        if not self.body or len(self.body) > 200_000:
            raise ValidationError("RFQ body is required and is too large.")
        if not self.products:
            raise ValidationError("RFQ must contain at least one product.")
        if len(self.generation_key) != 64:
            raise ValidationError("RFQ generation key must be a SHA-256 digest.")
        if self.generation_duration_ms < 0:
            raise ValidationError("RFQ generation duration cannot be negative.")
        self.to_recipients = _normalize_addresses(self.to_recipients)
        self.cc_recipients = _normalize_addresses(self.cc_recipients)
        self.bcc_recipients = _normalize_addresses(self.bcc_recipients)
        self.contact_name = _clean(self.contact_name, limit=255)
        self.observations = _clean(self.observations, limit=5000)
        self.cancellation_reason = _clean(self.cancellation_reason, limit=2000)
        for attribute in (
            "approved_at",
            "queued_at",
            "sending_started_at",
            "sent_at",
            "delivered_at",
            "cancelled_at",
        ):
            value = getattr(self, attribute)
            if value is not None:
                setattr(self, attribute, _as_utc(value))

    def _transition(self, target: RfqStatus) -> None:
        if target is self.status:
            return
        if target not in _RFQ_TRANSITIONS[self.status]:
            raise InvalidRfqState(
                f"RFQ cannot transition from {self.status.value} to {target.value}."
            )
        self.status = target
        self.updated_at = _now()

    def start_review(self) -> None:
        self._transition(RfqStatus.PENDING_REVIEW)

    def edit(
        self,
        *,
        subject: str | None = None,
        body: str | None = None,
        to_recipients: tuple[str, ...] | None = None,
        cc_recipients: tuple[str, ...] | None = None,
        bcc_recipients: tuple[str, ...] | None = None,
        response_deadline: datetime | None = None,
        observations: str | None = None,
        contact_name: str | None = None,
    ) -> None:
        if self.status not in {RfqStatus.DRAFT, RfqStatus.PENDING_REVIEW}:
            raise InvalidRfqState("Only draft or pending-review RFQs can be edited.")
        changed = False
        if subject is not None:
            cleaned = subject.strip()
            if not cleaned or len(cleaned) > 998:
                raise ValidationError("RFQ subject is invalid.")
            changed |= cleaned != self.subject
            self.subject = cleaned
        if body is not None:
            cleaned = body.strip()
            if not cleaned or len(cleaned) > 200_000:
                raise ValidationError("RFQ body is invalid.")
            changed |= cleaned != self.body
            self.body = cleaned
        if to_recipients is not None:
            normalized = _normalize_addresses(to_recipients)
            changed |= normalized != self.to_recipients
            self.to_recipients = normalized
        if cc_recipients is not None:
            normalized = _normalize_addresses(cc_recipients)
            changed |= normalized != self.cc_recipients
            self.cc_recipients = normalized
        if bcc_recipients is not None:
            normalized = _normalize_addresses(bcc_recipients)
            changed |= normalized != self.bcc_recipients
            self.bcc_recipients = normalized
        if response_deadline is not None:
            normalized = _as_utc(response_deadline)
            if normalized <= _now():
                raise ValidationError("RFQ response deadline must be in the future.")
            changed |= normalized != self.response_deadline
            self.response_deadline = normalized
        if observations is not None:
            normalized = _clean(observations, limit=5000)
            changed |= normalized != self.observations
            self.observations = normalized
        if contact_name is not None:
            normalized = _clean(contact_name, limit=255)
            changed |= normalized != self.contact_name
            self.contact_name = normalized
        if changed:
            self.version += 1
            self.updated_at = _now()

    def record_attachment_edit(self) -> None:
        if self.status not in {RfqStatus.DRAFT, RfqStatus.PENDING_REVIEW}:
            raise InvalidRfqState("Only draft or pending-review RFQs can be edited.")
        self.version += 1
        self.updated_at = _now()

    def approve(self, user_id: UUID, attachments: tuple[EmailAttachment, ...]) -> None:
        if self.status is not RfqStatus.PENDING_REVIEW:
            raise InvalidRfqState("Only pending-review RFQs can be approved.")
        if not self.to_recipients:
            raise ValidationError("RFQ requires at least one primary recipient before approval.")
        digest_payload = {
            "rfq_id": str(self.id),
            "version": self.version,
            "to": self.to_recipients,
            "cc": self.cc_recipients,
            "bcc": self.bcc_recipients,
            "subject": self.subject,
            "body": self.body,
            "deadline": self.response_deadline.isoformat(),
            "attachments": [attachment.snapshot() for attachment in attachments],
        }
        encoded = json.dumps(digest_payload, sort_keys=True, separators=(",", ":")).encode()
        self.send_idempotency_key = hashlib.sha256(encoded).hexdigest()
        self._transition(RfqStatus.APPROVED)
        self.approved_by_user_id = user_id
        self.approved_at = self.updated_at

    def queue(self, user_id: UUID) -> None:
        if self.send_idempotency_key is None:
            raise InvalidRfqState("RFQ must be approved before it can be queued.")
        self._transition(RfqStatus.QUEUED)
        self.send_requested_by_user_id = user_id
        self.queued_at = self.updated_at
        self.last_error = None

    def start_sending(self) -> None:
        self._transition(RfqStatus.SENDING)
        self.sending_started_at = self.updated_at

    def mark_sent(self) -> None:
        self._transition(RfqStatus.SENT)
        self.sent_at = self.updated_at
        self.last_error = None

    def mark_delivered(self) -> None:
        self._transition(RfqStatus.DELIVERED)
        self.delivered_at = self.updated_at

    def mark_failed(self, error: str) -> None:
        self._transition(RfqStatus.FAILED)
        self.last_error = (_clean(error, limit=4000) or "Email delivery failed.")

    def cancel(self, user_id: UUID, reason: str | None = None) -> None:
        self._transition(RfqStatus.CANCELLED)
        self.cancelled_by_user_id = user_id
        self.cancelled_at = self.updated_at
        self.cancellation_reason = _clean(reason, limit=2000)


@dataclass(slots=True)
class EmailMessage:
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
    body: str
    attachment_snapshot: tuple[dict[str, Any], ...]
    status: EmailMessageStatus = EmailMessageStatus.QUEUED
    id: UUID = field(default_factory=uuid4)
    external_message_id: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    sent_at: datetime | None = None
    duration_ms: int | None = None
    created_at: datetime = field(default_factory=_now)

    def __post_init__(self) -> None:
        if self.rfq_version < 1 or self.attempt_number < 1:
            raise ValidationError("Email RFQ version and attempt number must be positive.")
        if len(self.idempotency_key) != 64:
            raise ValidationError("Email idempotency key must be a SHA-256 digest.")
        self.from_address = EmailAddress(self.from_address).value
        self.to_recipients = _normalize_addresses(self.to_recipients)
        self.cc_recipients = _normalize_addresses(self.cc_recipients)
        self.bcc_recipients = _normalize_addresses(self.bcc_recipients)
        if not self.to_recipients:
            raise ValidationError("Email message requires a primary recipient.")
        if not self.subject.strip() or not self.body.strip():
            raise ValidationError("Email message subject and body are required.")
        self.created_at = _as_utc(self.created_at)

    def start(self) -> None:
        if self.status is not EmailMessageStatus.QUEUED:
            raise InvalidRfqState("Only queued email messages can start sending.")
        self.status = EmailMessageStatus.SENDING
        self.started_at = _now()

    def succeed(self, external_message_id: str, duration_ms: int) -> None:
        if self.status is not EmailMessageStatus.SENDING:
            raise InvalidRfqState("Only sending messages can be marked sent.")
        identifier = _clean(external_message_id, limit=1000)
        if not identifier:
            raise ValidationError("Email provider message identifier is required.")
        self.status = EmailMessageStatus.SENT
        self.external_message_id = identifier
        self.duration_ms = max(duration_ms, 0)
        self.sent_at = _now()
        self.error_type = None
        self.error_message = None

    def fail(self, error: Exception, duration_ms: int) -> None:
        if self.status is not EmailMessageStatus.SENDING:
            raise InvalidRfqState("Only sending messages can fail.")
        self.status = EmailMessageStatus.FAILED
        self.error_type = type(error).__name__
        self.error_message = str(error)[:4000]
        self.duration_ms = max(duration_ms, 0)


@dataclass(frozen=True, slots=True)
class OutboundMessageLog:
    rfq_id: UUID
    email_message_id: UUID
    event_type: str
    result: OutboundLogResult
    provider_name: str
    details: dict[str, Any]
    id: UUID = field(default_factory=uuid4)
    occurred_at: datetime = field(default_factory=_now)

    def __post_init__(self) -> None:
        if not _clean(self.event_type, limit=100):
            raise ValidationError("Outbound message log event type is required.")
        if not _clean(self.provider_name, limit=255):
            raise ValidationError("Outbound message provider name is required.")
