"""harden document subsystem traceability

Revision ID: c8f3a05d6e94
Revises: b7e2f94c5d83
Create Date: 2026-08-12 12:20:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c8f3a05d6e94"
down_revision: str | None = "b7e2f94c5d83"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("extraction_runs") as batch_op:
        batch_op.add_column(
            sa.Column(
                "extraction_type",
                sa.String(length=30),
                nullable=False,
                server_default=sa.text("'text'"),
            )
        )

    with op.batch_alter_table("extraction_runs") as batch_op:
        batch_op.alter_column("extraction_type", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("extraction_runs") as batch_op:
        batch_op.drop_column("extraction_type")
