from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.infrastructure.db.base import Base


class RfqRequestModel(Base):
    __tablename__ = "rfq_requests"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'pending_review', 'approved', 'queued', 'sending', "
            "'sent', 'delivered', 'responded', 'failed', 'retry_pending', 'cancelled')",
            name="valid_rfq_status",
        ),
        UniqueConstraint("tender_id", "generation_key", name="uq_rfq_tender_generation"),
        UniqueConstraint("send_idempotency_key", name="uq_rfq_send_idempotency"),
        Index("ix_rfq_requests_tender", "tender_id"),
        Index("ix_rfq_requests_supplier", "tender_supplier_id"),
        Index("ix_rfq_requests_contact", "contact_id"),
        Index("ix_rfq_requests_status", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tender_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("tenders.id", ondelete="CASCADE"), nullable=False
    )
    tender_supplier_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("tender_suppliers.id", ondelete="RESTRICT"), nullable=False
    )
    supplier_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False
    )
    contact_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("supplier_contacts.id", ondelete="RESTRICT"), nullable=True
    )
    catalog_snapshot_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("catalog_snapshots.id", ondelete="RESTRICT"), nullable=False
    )
    generated_by_user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    response_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    template_name: Mapped[str] = mapped_column(String(100), nullable=False)
    template_version: Mapped[str] = mapped_column(String(50), nullable=False)
    subject: Mapped[str] = mapped_column(String(998), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    products: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    generation_key: Mapped[str] = mapped_column(String(64), nullable=False)
    generation_duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    to_recipients: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    cc_recipients: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    bcc_recipients: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    observations: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    approved_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    send_requested_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sending_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    send_idempotency_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class RfqVersionModel(Base):
    __tablename__ = "rfq_versions"
    __table_args__ = (
        UniqueConstraint("rfq_id", "version", name="uq_rfq_versions_rfq_version"),
        Index("ix_rfq_versions_rfq", "rfq_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    rfq_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("rfq_requests.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    changed_by_user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    contact_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("supplier_contacts.id", ondelete="RESTRICT"), nullable=True
    )
    subject: Mapped[str] = mapped_column(String(998), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    to_recipients: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    cc_recipients: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    bcc_recipients: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    products: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    attachment_snapshot: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    change_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class EmailAttachmentModel(Base):
    __tablename__ = "email_attachments"
    __table_args__ = (
        UniqueConstraint("rfq_id", "document_id", name="uq_rfq_attachment_document"),
        Index("ix_email_attachments_rfq", "rfq_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    rfq_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("rfq_requests.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("tender_documents.id", ondelete="RESTRICT"), nullable=False
    )
    original_file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class EmailMessageModel(Base):
    __tablename__ = "email_messages"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'sending', 'sent', 'failed', 'bounced')",
            name="valid_email_message_status",
        ),
        UniqueConstraint("rfq_id", "attempt_number", name="uq_email_message_attempt"),
        UniqueConstraint("idempotency_key", name="uq_email_messages_idempotency_key"),
        Index("ix_email_messages_rfq", "rfq_id"),
        Index("ix_email_messages_idempotency", "idempotency_key"),
        Index("ix_email_messages_status", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    rfq_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("rfq_requests.id", ondelete="CASCADE"), nullable=False
    )
    rfq_version: Mapped[int] = mapped_column(Integer, nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_name: Mapped[str] = mapped_column(String(255), nullable=False)
    from_address: Mapped[str] = mapped_column(String(320), nullable=False)
    to_recipients: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    cc_recipients: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    bcc_recipients: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    subject: Mapped[str] = mapped_column(String(998), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    attachment_snapshot: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    external_message_id: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RfqTaskRecordModel(Base):
    __tablename__ = "rfq_task_records"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'retry_pending')",
            name="valid_rfq_task_status",
        ),
        UniqueConstraint("correlation_id", name="uq_rfq_task_records_correlation"),
        Index("ix_rfq_task_records_rfq", "rfq_id"),
        Index("ix_rfq_task_records_status", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    rfq_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("rfq_requests.id", ondelete="CASCADE"), nullable=False
    )
    correlation_id: Mapped[str] = mapped_column(String(255), nullable=False)
    task_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OutboundMessageLogModel(Base):
    __tablename__ = "outbound_message_logs"
    __table_args__ = (
        CheckConstraint(
            "result IN ('recorded', 'success', 'failure')",
            name="valid_outbound_message_result",
        ),
        Index("ix_outbound_logs_rfq", "rfq_id"),
        Index("ix_outbound_logs_message", "email_message_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    rfq_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("rfq_requests.id", ondelete="CASCADE"), nullable=False
    )
    email_message_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("email_messages.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    result: Mapped[str] = mapped_column(String(20), nullable=False)
    provider_name: Mapped[str] = mapped_column(String(255), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
