"""add manual quote intake, evidence and review history

Revision ID: f2b8c47d1e90
Revises: e1a7b32c9d65
Create Date: 2026-08-09 10:45:00
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision: str = "f2b8c47d1e90"
down_revision: str | None = "e1a7b32c9d65"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _replace_check(table: str, name: str, expression: str) -> None:
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table(table) as batch_op:
            batch_op.drop_constraint(name, type_="check")
            batch_op.create_check_constraint(name, expression)
    else:
        op.drop_constraint(name, table, type_="check")
        op.create_check_constraint(name, table, expression)


def upgrade() -> None:
    with op.batch_alter_table("quotes") as batch_op:
        batch_op.add_column(sa.Column("rfq_request_id", sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column("currency", sa.String(length=3), nullable=True))
        batch_op.add_column(sa.Column("subtotal_amount", sa.Numeric(24, 6), nullable=True))
        batch_op.add_column(sa.Column("tax_amount", sa.Numeric(24, 6), nullable=True))
        batch_op.add_column(sa.Column("total_amount", sa.Numeric(24, 6), nullable=True))
        batch_op.add_column(sa.Column("delivery_time_days", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("commercial_terms", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("received_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("approved_extraction_run_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            "fk_quotes_rfq_request_id_rfq_requests",
            "rfq_requests",
            ["rfq_request_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_quotes_rfq_request_id", ["rfq_request_id"])

    op.execute("UPDATE quotes SET received_at = created_at WHERE received_at IS NULL")
    with op.batch_alter_table("quotes") as batch_op:
        batch_op.alter_column("received_at", nullable=False)

    _replace_check(
        "quotes",
        "valid_quote_status",
        "status IN ('received', 'validating', 'extracting', 'extracted', 'normalized', "
        "'pending_review', 'approved', 'rejected', 'failed', 'included_in_comparison')",
    )

    op.create_table(
        "quote_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("quote_id", sa.Uuid(), nullable=False),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column("original_file_name", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=255), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("file_hash", sa.String(length=64), nullable=False),
        sa.Column("document_type", sa.String(length=20), nullable=False),
        sa.Column("processing_status", sa.String(length=30), nullable=False),
        sa.Column("extractor_name", sa.String(length=100), nullable=True),
        sa.Column("extractor_version", sa.String(length=100), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["quote_id"], ["quotes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("quote_id", "file_hash", name="uq_quote_documents_quote_hash"),
    )
    op.create_index("ix_quote_documents_quote_id", "quote_documents", ["quote_id"])
    op.create_index("ix_quote_documents_hash", "quote_documents", ["file_hash"])
    op.create_index("ix_quote_documents_status", "quote_documents", ["processing_status"])

    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, storage_key, original_file_name, mime_type, file_size, file_hash, created_at, updated_at FROM quotes"
        )
    ).mappings()
    for row in rows:
        mime = (row["mime_type"] or "").lower()
        document_type = "xlsx" if "spreadsheet" in mime else "docx" if "wordprocessingml" in mime else "pdf"
        bind.execute(
            sa.text(
                "INSERT INTO quote_documents "
                "(id, quote_id, storage_key, original_file_name, mime_type, file_size, file_hash, document_type, processing_status, created_at, updated_at) "
                "VALUES (:id, :quote_id, :storage_key, :name, :mime, :size, :hash, :type, 'processed', :created, :updated)"
            ),
            {
                "id": uuid4(),
                "quote_id": row["id"],
                "storage_key": row["storage_key"],
                "name": row["original_file_name"],
                "mime": row["mime_type"],
                "size": row["file_size"],
                "hash": row["file_hash"],
                "type": document_type,
                "created": row["created_at"],
                "updated": row["updated_at"],
            },
        )

    with op.batch_alter_table("quote_extraction_runs") as batch_op:
        batch_op.add_column(sa.Column("quote_document_id", sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column("extraction_fingerprint", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("run_number", sa.Integer(), server_default="1", nullable=False))
        batch_op.add_column(sa.Column("provider", sa.String(length=100), server_default="openai", nullable=False))
        batch_op.add_column(sa.Column("extractor_name", sa.String(length=100), server_default="unknown", nullable=False))
        batch_op.add_column(sa.Column("duration_ms", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("reused_from_run_id", sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column("is_approved_source", sa.Boolean(), server_default=sa.false(), nullable=False))
        batch_op.create_foreign_key(
            "fk_quote_runs_document",
            "quote_documents",
            ["quote_document_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_foreign_key(
            "fk_quote_runs_reused",
            "quote_extraction_runs",
            ["reused_from_run_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_quote_runs_document_id", ["quote_document_id"])
        batch_op.create_index("ix_quote_runs_fingerprint", ["extraction_fingerprint"])

    bind.execute(
        sa.text(
            "UPDATE quote_extraction_runs r SET quote_document_id = "
            "(SELECT d.id FROM quote_documents d WHERE d.quote_id = r.quote_id ORDER BY d.created_at LIMIT 1) "
            "WHERE quote_document_id IS NULL"
        ) if bind.dialect.name == "postgresql" else sa.text(
            "UPDATE quote_extraction_runs SET quote_document_id = "
            "(SELECT d.id FROM quote_documents d WHERE d.quote_id = quote_extraction_runs.quote_id ORDER BY d.created_at LIMIT 1) "
            "WHERE quote_document_id IS NULL"
        )
    )

    op.create_table(
        "quote_evidence_references",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("quote_id", sa.Uuid(), nullable=False),
        sa.Column("quote_document_id", sa.Uuid(), nullable=False),
        sa.Column("extraction_run_id", sa.Uuid(), nullable=False),
        sa.Column("entity_type", sa.String(length=30), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("field_name", sa.String(length=100), nullable=False),
        sa.Column("locator_type", sa.String(length=30), nullable=False),
        sa.Column("locator", sa.String(length=255), nullable=False),
        sa.Column("fragment", sa.Text(), nullable=False),
        sa.Column("extraction_method", sa.String(length=100), nullable=False),
        sa.Column("finding_status", sa.String(length=30), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["quote_id"], ["quotes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["quote_document_id"], ["quote_documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["extraction_run_id"], ["quote_extraction_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_quote_evidence_quote_id", "quote_evidence_references", ["quote_id"])
    op.create_index("ix_quote_evidence_document_id", "quote_evidence_references", ["quote_document_id"])
    op.create_index("ix_quote_evidence_run_id", "quote_evidence_references", ["extraction_run_id"])
    op.create_index("ix_quote_evidence_entity", "quote_evidence_references", ["entity_type", "entity_id"])

    with op.batch_alter_table("quote_items") as batch_op:
        batch_op.add_column(sa.Column("extraction_run_id", sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column("description", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("unit", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("quoted_specifications", sa.JSON(), server_default="{}", nullable=False))
        batch_op.add_column(sa.Column("compliance_status", sa.String(length=30), server_default="unknown", nullable=False))
        batch_op.add_column(sa.Column("match_status", sa.String(length=30), server_default="unmatched", nullable=False))
        batch_op.add_column(sa.Column("match_score", sa.Float(), server_default="0", nullable=False))
        batch_op.add_column(sa.Column("match_reason", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("warnings", sa.JSON(), server_default="[]", nullable=False))
        batch_op.add_column(sa.Column("source_evidence_id", sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column("original_extracted", sa.JSON(), server_default="{}", nullable=False))
        batch_op.add_column(sa.Column("is_current", sa.Boolean(), server_default=sa.true(), nullable=False))
        batch_op.add_column(sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_foreign_key("fk_quote_items_run", "quote_extraction_runs", ["extraction_run_id"], ["id"], ondelete="SET NULL")
        batch_op.create_foreign_key("fk_quote_items_evidence", "quote_evidence_references", ["source_evidence_id"], ["id"], ondelete="SET NULL")
        batch_op.create_index("ix_quote_items_run_id", ["extraction_run_id"])
        batch_op.create_index("ix_quote_items_current", ["quote_id", "is_current"])
    op.execute("UPDATE quote_items SET updated_at = created_at WHERE updated_at IS NULL")
    op.execute("UPDATE quote_items SET compliance_status = CASE WHEN technical_compliance = TRUE THEN 'compliant' WHEN technical_compliance = FALSE THEN 'non_compliant' ELSE 'unknown' END")
    op.execute("UPDATE quote_items SET match_status = 'matched', match_score = 1 WHERE catalog_product_id IS NOT NULL")
    with op.batch_alter_table("quote_items") as batch_op:
        batch_op.alter_column("updated_at", nullable=False)

    op.create_table(
        "quote_item_revisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("quote_id", sa.Uuid(), nullable=False),
        sa.Column("quote_item_id", sa.Uuid(), nullable=False),
        sa.Column("changed_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("before", sa.JSON(), nullable=False),
        sa.Column("after", sa.JSON(), nullable=False),
        sa.Column("changed_fields", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["quote_id"], ["quotes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["quote_item_id"], ["quote_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["changed_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_quote_item_revisions_quote", "quote_item_revisions", ["quote_id"])
    op.create_index("ix_quote_item_revisions_item", "quote_item_revisions", ["quote_item_id"])

    op.create_table(
        "quote_task_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("quote_id", sa.Uuid(), nullable=False),
        sa.Column("correlation_id", sa.String(length=255), nullable=False),
        sa.Column("task_name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("force_reprocess", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('queued', 'running', 'succeeded', 'failed', 'retry_pending')", name="valid_quote_task_status"),
        sa.ForeignKeyConstraint(["quote_id"], ["quotes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("correlation_id", name="uq_quote_task_records_correlation"),
    )
    op.create_index("ix_quote_task_records_quote", "quote_task_records", ["quote_id"])
    op.create_index("ix_quote_task_records_status", "quote_task_records", ["status"])

    with op.batch_alter_table("quotes") as batch_op:
        batch_op.create_foreign_key(
            "fk_quotes_approved_extraction_run",
            "quote_extraction_runs",
            ["approved_extraction_run_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("quotes") as batch_op:
        batch_op.drop_constraint("fk_quotes_approved_extraction_run", type_="foreignkey")
    op.drop_index("ix_quote_task_records_status", table_name="quote_task_records")
    op.drop_index("ix_quote_task_records_quote", table_name="quote_task_records")
    op.drop_table("quote_task_records")
    op.drop_index("ix_quote_item_revisions_item", table_name="quote_item_revisions")
    op.drop_index("ix_quote_item_revisions_quote", table_name="quote_item_revisions")
    op.drop_table("quote_item_revisions")
    with op.batch_alter_table("quote_items") as batch_op:
        batch_op.drop_index("ix_quote_items_current")
        batch_op.drop_index("ix_quote_items_run_id")
        batch_op.drop_constraint("fk_quote_items_evidence", type_="foreignkey")
        batch_op.drop_constraint("fk_quote_items_run", type_="foreignkey")
        for column in ("updated_at", "is_current", "original_extracted", "source_evidence_id", "warnings", "match_reason", "match_score", "match_status", "compliance_status", "quoted_specifications", "unit", "description", "extraction_run_id"):
            batch_op.drop_column(column)
    op.drop_index("ix_quote_evidence_entity", table_name="quote_evidence_references")
    op.drop_index("ix_quote_evidence_run_id", table_name="quote_evidence_references")
    op.drop_index("ix_quote_evidence_document_id", table_name="quote_evidence_references")
    op.drop_index("ix_quote_evidence_quote_id", table_name="quote_evidence_references")
    op.drop_table("quote_evidence_references")
    with op.batch_alter_table("quote_extraction_runs") as batch_op:
        batch_op.drop_index("ix_quote_runs_fingerprint")
        batch_op.drop_index("ix_quote_runs_document_id")
        batch_op.drop_constraint("fk_quote_runs_reused", type_="foreignkey")
        batch_op.drop_constraint("fk_quote_runs_document", type_="foreignkey")
        for column in ("is_approved_source", "reused_from_run_id", "duration_ms", "extractor_name", "provider", "run_number", "extraction_fingerprint", "quote_document_id"):
            batch_op.drop_column(column)
    op.drop_index("ix_quote_documents_status", table_name="quote_documents")
    op.drop_index("ix_quote_documents_hash", table_name="quote_documents")
    op.drop_index("ix_quote_documents_quote_id", table_name="quote_documents")
    op.drop_table("quote_documents")
    _replace_check(
        "quotes",
        "valid_quote_status",
        "status IN ('received', 'validating', 'extracting', 'extracted', 'normalized', "
        "'pending_review', 'approved', 'rejected', 'included_in_comparison')",
    )
    with op.batch_alter_table("quotes") as batch_op:
        batch_op.drop_index("ix_quotes_rfq_request_id")
        batch_op.drop_constraint("fk_quotes_rfq_request_id_rfq_requests", type_="foreignkey")
        for column in ("approved_extraction_run_id", "received_at", "valid_until", "commercial_terms", "delivery_time_days", "total_amount", "tax_amount", "subtotal_amount", "currency", "rfq_request_id"):
            batch_op.drop_column(column)
