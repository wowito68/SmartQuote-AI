"""harden RFQ workflow, version history and delivery idempotency

Revision ID: e1a7b32c9d65
Revises: d0f6a21b8c54
Create Date: 2026-08-08 23:55:00
"""

from collections.abc import Sequence
import hashlib

import sqlalchemy as sa
from alembic import op

revision: str = "e1a7b32c9d65"
down_revision: str | None = "d0f6a21b8c54"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _replace_check(table: str, name: str, expression: str) -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table(table) as batch_op:
            batch_op.drop_constraint(name, type_="check")
            batch_op.create_check_constraint(name, expression)
    else:
        op.drop_constraint(name, table, type_="check")
        op.create_check_constraint(name, table, expression)


def _reconcile_legacy_message_idempotency() -> None:
    """Make legacy retry rows unique before adding the database constraint.

    Iteration 8 allowed multiple transport attempts to share the RFQ send key. The
    hardened model reuses one EmailMessage for retries. Existing duplicate rows are
    retained, but only one keeps the canonical key; the others receive deterministic
    SHA-256 legacy keys so no history is deleted.
    """
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT idempotency_key FROM email_messages "
            "GROUP BY idempotency_key HAVING COUNT(*) > 1"
        )
    ).fetchall()
    for (key,) in rows:
        attempts = bind.execute(
            sa.text(
                "SELECT id, status FROM email_messages "
                "WHERE idempotency_key = :key "
                "ORDER BY CASE WHEN status = 'sent' THEN 0 ELSE 1 END, attempt_number, created_at"
            ),
            {"key": key},
        ).fetchall()
        for message_id, _status in attempts[1:]:
            replacement = hashlib.sha256(
                f"legacy-email-attempt|{key}|{message_id}".encode()
            ).hexdigest()
            bind.execute(
                sa.text(
                    "UPDATE email_messages SET idempotency_key = :replacement WHERE id = :id"
                ),
                {"replacement": replacement, "id": message_id},
            )


def upgrade() -> None:
    with op.batch_alter_table("rfq_requests") as batch_op:
        batch_op.add_column(sa.Column("contact_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            "fk_rfq_requests_contact_id_supplier_contacts",
            "supplier_contacts",
            ["contact_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_index("ix_rfq_requests_contact", ["contact_id"])

    # Iteration 9 renamed this constraint to `valid_rfq_status`; keep the
    # logical constraint name stable so the naming convention is applied once.
    _replace_check(
        "rfq_requests",
        "valid_rfq_status",
        "status IN ('draft', 'pending_review', 'approved', 'queued', 'sending', "
        "'sent', 'delivered', 'responded', 'failed', 'retry_pending', 'cancelled')",
    )

    with op.batch_alter_table("email_messages") as batch_op:
        batch_op.add_column(sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True))

    _reconcile_legacy_message_idempotency()

    with op.batch_alter_table("email_messages") as batch_op:
        batch_op.create_unique_constraint(
            "uq_email_messages_idempotency_key",
            ["idempotency_key"],
        )

    _replace_check(
        "email_messages",
        "valid_email_message_status",
        "status IN ('queued', 'sending', 'sent', 'failed', 'bounced')",
    )

    op.create_table(
        "rfq_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("rfq_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("changed_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("contact_id", sa.Uuid(), nullable=True),
        sa.Column("subject", sa.String(length=998), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("to_recipients", sa.JSON(), nullable=False),
        sa.Column("cc_recipients", sa.JSON(), nullable=False),
        sa.Column("bcc_recipients", sa.JSON(), nullable=False),
        sa.Column("products", sa.JSON(), nullable=False),
        sa.Column("attachment_snapshot", sa.JSON(), nullable=False),
        sa.Column("change_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["rfq_id"], ["rfq_requests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["changed_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["contact_id"], ["supplier_contacts.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("rfq_id", "version", name="uq_rfq_versions_rfq_version"),
    )
    op.create_index("ix_rfq_versions_rfq", "rfq_versions", ["rfq_id"])

    op.create_table(
        "rfq_task_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("rfq_id", sa.Uuid(), nullable=False),
        sa.Column("correlation_id", sa.String(length=255), nullable=False),
        sa.Column("task_name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'retry_pending')",
            name="valid_rfq_task_status",
        ),
        sa.ForeignKeyConstraint(["rfq_id"], ["rfq_requests.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("correlation_id", name="uq_rfq_task_records_correlation"),
    )
    op.create_index("ix_rfq_task_records_rfq", "rfq_task_records", ["rfq_id"])
    op.create_index("ix_rfq_task_records_status", "rfq_task_records", ["status"])


def downgrade() -> None:
    op.drop_index("ix_rfq_task_records_status", table_name="rfq_task_records")
    op.drop_index("ix_rfq_task_records_rfq", table_name="rfq_task_records")
    op.drop_table("rfq_task_records")
    op.drop_index("ix_rfq_versions_rfq", table_name="rfq_versions")
    op.drop_table("rfq_versions")

    _replace_check(
        "email_messages",
        "valid_email_message_status",
        "status IN ('queued', 'sending', 'sent', 'failed')",
    )
    with op.batch_alter_table("email_messages") as batch_op:
        batch_op.drop_constraint("uq_email_messages_idempotency_key", type_="unique")
        batch_op.drop_column("failed_at")

    _replace_check(
        "rfq_requests",
        "valid_rfq_status",
        "status IN ('draft', 'pending_review', 'approved', 'queued', 'sending', "
        "'sent', 'delivered', 'responded', 'failed', 'cancelled')",
    )
    with op.batch_alter_table("rfq_requests") as batch_op:
        batch_op.drop_index("ix_rfq_requests_contact")
        batch_op.drop_constraint(
            "fk_rfq_requests_contact_id_supplier_contacts",
            type_="foreignkey",
        )
        batch_op.drop_column("contact_id")
