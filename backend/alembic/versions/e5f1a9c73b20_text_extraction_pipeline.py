"""add asynchronous text extraction pipeline

Revision ID: e5f1a9c73b20
Revises: d914a6b4f2c1
Create Date: 2026-07-25 14:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e5f1a9c73b20"
down_revision: str | None = "d914a6b4f2c1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_STATUS_CONSTRAINT = "processing_status IN ('uploaded', 'deleted', 'rejected')"
NEW_STATUS_CONSTRAINT = (
    "processing_status IN ('uploaded', 'queued', 'processing', 'text_extracted', "
    "'ready_for_ai', 'needs_ocr', 'failed', 'deleted', 'rejected')"
)


def _replace_document_status_constraint(expression: str) -> None:
    recreate = "always" if op.get_bind().dialect.name == "sqlite" else "auto"
    with op.batch_alter_table("tender_documents", recreate=recreate) as batch_op:
        batch_op.drop_constraint(
            op.f("ck_tender_documents_valid_document_status"),
            type_="check",
        )
        batch_op.create_check_constraint("valid_document_status", expression)


def upgrade() -> None:
    _replace_document_status_constraint(NEW_STATUS_CONSTRAINT)
    with op.batch_alter_table("tender_documents") as batch_op:
        batch_op.add_column(sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(
            sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("last_processing_error", sa.Text(), nullable=True))
        batch_op.create_index(
            "ix_tender_documents_processing_status", ["processing_status"], unique=False
        )

    op.create_table(
        "extraction_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("processing_key", sa.String(length=64), nullable=False),
        sa.Column("extractor_name", sa.String(length=100), nullable=False),
        sa.Column("extractor_version", sa.String(length=100), nullable=False),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.BigInteger(), nullable=True),
        sa.Column("pages_processed", sa.Integer(), nullable=False),
        sa.Column("characters_extracted", sa.BigInteger(), nullable=False),
        sa.Column("error_type", sa.String(length=255), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("reused_from_run_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('running', 'completed', 'failed', 'reused')",
            name=op.f("ck_extraction_runs_valid_extraction_run_status"),
        ),
        sa.ForeignKeyConstraint(["document_id"], ["tender_documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["reused_from_run_id"],
            ["extraction_runs.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_id", "processing_key", name="uq_extraction_runs_document_processing_key"
        ),
    )
    op.create_index("ix_extraction_runs_document_id", "extraction_runs", ["document_id"])
    op.create_index("ix_extraction_runs_status", "extraction_runs", ["status"])

    op.create_table(
        "document_pages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("extraction_run_id", sa.Uuid(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("width", sa.Float(), nullable=False),
        sa.Column("height", sa.Float(), nullable=False),
        sa.Column("character_count", sa.BigInteger(), nullable=False),
        sa.Column("word_count", sa.BigInteger(), nullable=False),
        sa.Column("is_empty", sa.Boolean(), nullable=False),
        sa.Column("text_density", sa.Float(), nullable=False),
        sa.Column("duration_ms", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "page_number > 0",
            name=op.f("ck_document_pages_positive_document_page_number"),
        ),
        sa.ForeignKeyConstraint(["document_id"], ["tender_documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["extraction_run_id"], ["extraction_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("extraction_run_id", "page_number", name="uq_document_pages_run_page"),
    )
    op.create_index("ix_document_pages_document_id", "document_pages", ["document_id"])
    op.create_index("ix_document_pages_extraction_run_id", "document_pages", ["extraction_run_id"])

    op.create_table(
        "document_qualities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("extraction_run_id", sa.Uuid(), nullable=False),
        sa.Column("pages_processed", sa.Integer(), nullable=False),
        sa.Column("empty_pages", sa.Integer(), nullable=False),
        sa.Column("characters_extracted", sa.BigInteger(), nullable=False),
        sa.Column("empty_page_percentage", sa.Float(), nullable=False),
        sa.Column("text_density", sa.Float(), nullable=False),
        sa.Column("quality_level", sa.String(length=20), nullable=False),
        sa.Column("decision", sa.String(length=30), nullable=False),
        sa.Column("requires_manual_review", sa.Boolean(), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "quality_level IN ('high', 'medium', 'low')",
            name=op.f("ck_document_qualities_valid_document_quality_level"),
        ),
        sa.CheckConstraint(
            "decision IN ('ready_for_ai', 'needs_ocr', 'manual_review')",
            name=op.f("ck_document_qualities_valid_document_quality_decision"),
        ),
        sa.ForeignKeyConstraint(["document_id"], ["tender_documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["extraction_run_id"], ["extraction_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("extraction_run_id", name="uq_document_qualities_extraction_run"),
    )
    op.create_index("ix_document_qualities_document_id", "document_qualities", ["document_id"])


def downgrade() -> None:
    op.drop_index("ix_document_qualities_document_id", table_name="document_qualities")
    op.drop_table("document_qualities")
    op.drop_index("ix_document_pages_extraction_run_id", table_name="document_pages")
    op.drop_index("ix_document_pages_document_id", table_name="document_pages")
    op.drop_table("document_pages")
    op.drop_index("ix_extraction_runs_status", table_name="extraction_runs")
    op.drop_index("ix_extraction_runs_document_id", table_name="extraction_runs")
    op.drop_table("extraction_runs")

    op.execute(
        "UPDATE tender_documents SET processing_status = 'uploaded' "
        "WHERE processing_status IN ('queued', 'processing', 'text_extracted', "
        "'ready_for_ai', 'needs_ocr', 'failed')"
    )
    with op.batch_alter_table("tender_documents") as batch_op:
        batch_op.drop_index("ix_tender_documents_processing_status")
        batch_op.drop_column("last_processing_error")
        batch_op.drop_column("processed_at")
        batch_op.drop_column("processing_started_at")
        batch_op.drop_column("queued_at")
    _replace_document_status_constraint(OLD_STATUS_CONSTRAINT)
