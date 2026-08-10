"""consolidate quote AI analysis contract

Revision ID: a6d1e83f4b72
Revises: f2b8c47d1e90
Create Date: 2026-08-10 10:45:00
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision: str = "a6d1e83f4b72"
down_revision: str | None = "f2b8c47d1e90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _replace_check(table: str, name: str, expression: str) -> None:
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table(table) as batch_op:
            batch_op.drop_constraint(name, type_="check")
            batch_op.create_check_constraint(name, expression)
        return
    op.drop_constraint(name, table, type_="check")
    op.create_check_constraint(name, table, expression)


def upgrade() -> None:
    _replace_check(
        "quotes",
        "valid_quote_status",
        "status IN ('received', 'validating', 'ready_for_analysis', 'analyzing', "
        "'analyzed', 'extracting', 'extracted', 'normalized', 'pending_review', "
        "'approved', 'rejected', 'failed', 'included_in_comparison')",
    )
    _replace_check(
        "quote_extraction_runs",
        "valid_quote_extraction_run_status",
        "status IN ('queued', 'running', 'completed', 'failed', 'cancelled', 'reused')",
    )

    op.create_table(
        "quote_extraction_artifacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("extraction_run_id", sa.Uuid(), nullable=False),
        sa.Column("schema_version", sa.String(length=50), nullable=False),
        sa.Column("structured_output", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["extraction_run_id"],
            ["quote_extraction_runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "extraction_run_id",
            name="uq_quote_extraction_artifacts_run",
        ),
    )
    op.create_index(
        "ix_quote_extraction_artifacts_run",
        "quote_extraction_artifacts",
        ["extraction_run_id"],
    )

    artifact_table = sa.table(
        "quote_extraction_artifacts",
        sa.column("id", sa.Uuid()),
        sa.column("extraction_run_id", sa.Uuid()),
        sa.column("schema_version", sa.String()),
        sa.column("structured_output", sa.JSON()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    rows = op.get_bind().execute(
        sa.text(
            "SELECT id, schema_version, raw_response, completed_at, created_at "
            "FROM quote_extraction_runs "
            "WHERE status IN ('completed', 'reused') AND raw_response IS NOT NULL"
        )
    ).mappings()
    for row in rows:
        op.get_bind().execute(
            artifact_table.insert(),
            {
                "id": uuid4(),
                "extraction_run_id": row["id"],
                "schema_version": row["schema_version"],
                "structured_output": row["raw_response"],
                "created_at": row["completed_at"] or row["created_at"],
            },
        )


def downgrade() -> None:
    op.drop_index(
        "ix_quote_extraction_artifacts_run",
        table_name="quote_extraction_artifacts",
    )
    op.drop_table("quote_extraction_artifacts")

    _replace_check(
        "quote_extraction_runs",
        "valid_quote_extraction_run_status",
        "status IN ('queued', 'running', 'completed', 'failed', 'reused')",
    )
    _replace_check(
        "quotes",
        "valid_quote_status",
        "status IN ('received', 'validating', 'extracting', 'extracted', 'normalized', "
        "'pending_review', 'approved', 'rejected', 'failed', "
        "'included_in_comparison')",
    )
