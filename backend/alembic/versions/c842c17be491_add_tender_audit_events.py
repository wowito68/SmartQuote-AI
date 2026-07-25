"""add tender audit events

Revision ID: c842c17be491
Revises: 9f6e762a7fc6
Create Date: 2026-07-25 12:00:00
"""
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

import sqlalchemy as sa
from alembic import op

revision: str = "c842c17be491"
down_revision: str | None = "9f6e762a7fc6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
SYSTEM_USER_ID = UUID("00000000-0000-0000-0000-000000000001")


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("aggregate_type", sa.String(length=50), nullable=False),
        sa.Column("aggregate_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
    )
    op.create_index("ix_audit_events_aggregate_id", "audit_events", ["aggregate_id"], unique=False)
    users = sa.table(
        "users",
        sa.column("id", sa.Uuid()),
        sa.column("email", sa.String()),
        sa.column("full_name", sa.String()),
        sa.column("role", sa.String()),
        sa.column("is_active", sa.Boolean()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    timestamp = datetime(2026, 7, 25, tzinfo=UTC)
    op.bulk_insert(
        users,
        [
            {
                "id": SYSTEM_USER_ID,
                "email": "system@smartquote.local",
                "full_name": "SmartQuote System",
                "role": "system",
                "is_active": True,
                "created_at": timestamp,
                "updated_at": timestamp,
            }
        ],
    )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM users WHERE id = :id").bindparams(id=SYSTEM_USER_ID))
    op.drop_index("ix_audit_events_aggregate_id", table_name="audit_events")
    op.drop_table("audit_events")
