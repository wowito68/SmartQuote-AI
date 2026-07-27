"""add RFQ generation and outbound email delivery

Revision ID: b8d4e9f06a32
Revises: a7c3d8e95f21
Create Date: 2026-07-27 12:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b8d4e9f06a32"
down_revision: str | None = "a7c3d8e95f21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "rfq_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tender_id", sa.Uuid(), nullable=False),
        sa.Column("tender_supplier_id", sa.Uuid(), nullable=False),
        sa.Column("supplier_id", sa.Uuid(), nullable=False),
        sa.Column("catalog_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("generated_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("response_deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("template_name", sa.String(length=100), nullable=False),
        sa.Column("template_version", sa.String(length=50), nullable=False),
        sa.Column("subject", sa.String(length=998), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("products", sa.JSON(), nullable=False),
        sa.Column("generation_key", sa.String(length=64), nullable=False),
        sa.Column("generation_duration_ms", sa.Integer(), server_default="0", nullable=False),
        sa.Column("to_recipients", sa.JSON(), nullable=False),
        sa.Column("cc_recipients", sa.JSON(), nullable=False),
        sa.Column("bcc_recipients", sa.JSON(), nullable=False),
        sa.Column("contact_name", sa.String(length=255), nullable=True),
        sa.Column("observations", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("approved_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("send_requested_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sending_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("send_idempotency_key", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'pending_review', 'approved', 'queued', 'sending', "
            "'sent', 'delivered', 'failed', 'cancelled')",
            name=op.f("ck_rfq_requests_valid_rfq_status"),
        ),
        sa.ForeignKeyConstraint(["tender_id"], ["tenders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["tender_supplier_id"], ["tender_suppliers.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["catalog_snapshot_id"], ["catalog_snapshots.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["generated_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["approved_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["send_requested_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["cancelled_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tender_id", "generation_key", name="uq_rfq_tender_generation"),
        sa.UniqueConstraint("send_idempotency_key", name="uq_rfq_send_idempotency"),
    )
    op.create_index("ix_rfq_requests_tender", "rfq_requests", ["tender_id"])
    op.create_index("ix_rfq_requests_supplier", "rfq_requests", ["tender_supplier_id"])
    op.create_index("ix_rfq_requests_status", "rfq_requests", ["status"])

    op.create_table(
        "email_attachments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("rfq_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("original_file_name", sa.String(length=255), nullable=False),
        sa.Column("file_hash", sa.String(length=64), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("mime_type", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["rfq_id"], ["rfq_requests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["document_id"], ["tender_documents.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("rfq_id", "document_id", name="uq_rfq_attachment_document"),
    )
    op.create_index("ix_email_attachments_rfq", "email_attachments", ["rfq_id"])

    op.create_table(
        "email_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("rfq_id", sa.Uuid(), nullable=False),
        sa.Column("rfq_version", sa.Integer(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("provider_name", sa.String(length=255), nullable=False),
        sa.Column("from_address", sa.String(length=320), nullable=False),
        sa.Column("to_recipients", sa.JSON(), nullable=False),
        sa.Column("cc_recipients", sa.JSON(), nullable=False),
        sa.Column("bcc_recipients", sa.JSON(), nullable=False),
        sa.Column("subject", sa.String(length=998), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("attachment_snapshot", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("external_message_id", sa.String(length=1000), nullable=True),
        sa.Column("error_type", sa.String(length=255), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('queued', 'sending', 'sent', 'failed')",
            name=op.f("ck_email_messages_valid_email_message_status"),
        ),
        sa.ForeignKeyConstraint(["rfq_id"], ["rfq_requests.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("rfq_id", "attempt_number", name="uq_email_message_attempt"),
    )
    op.create_index("ix_email_messages_rfq", "email_messages", ["rfq_id"])
    op.create_index("ix_email_messages_idempotency", "email_messages", ["idempotency_key"])
    op.create_index("ix_email_messages_status", "email_messages", ["status"])

    op.create_table(
        "outbound_message_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("rfq_id", sa.Uuid(), nullable=False),
        sa.Column("email_message_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("result", sa.String(length=20), nullable=False),
        sa.Column("provider_name", sa.String(length=255), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "result IN ('recorded', 'success', 'failure')",
            name=op.f("ck_outbound_message_logs_valid_outbound_message_result"),
        ),
        sa.ForeignKeyConstraint(["rfq_id"], ["rfq_requests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["email_message_id"], ["email_messages.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_outbound_logs_rfq", "outbound_message_logs", ["rfq_id"])
    op.create_index(
        "ix_outbound_logs_message", "outbound_message_logs", ["email_message_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_outbound_logs_message", table_name="outbound_message_logs")
    op.drop_index("ix_outbound_logs_rfq", table_name="outbound_message_logs")
    op.drop_table("outbound_message_logs")
    op.drop_index("ix_email_messages_status", table_name="email_messages")
    op.drop_index("ix_email_messages_idempotency", table_name="email_messages")
    op.drop_index("ix_email_messages_rfq", table_name="email_messages")
    op.drop_table("email_messages")
    op.drop_index("ix_email_attachments_rfq", table_name="email_attachments")
    op.drop_table("email_attachments")
    op.drop_index("ix_rfq_requests_status", table_name="rfq_requests")
    op.drop_index("ix_rfq_requests_supplier", table_name="rfq_requests")
    op.drop_index("ix_rfq_requests_tender", table_name="rfq_requests")
    op.drop_table("rfq_requests")
