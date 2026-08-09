"""harden manual quote reception, evidence and review

Revision ID: f2b8c41d7e90
Revises: e1a7b32c9d65
Create Date: 2026-08-09 18:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f2b8c41d7e90"
down_revision: str | None = "e1a7b32c9d65"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _replace_quote_status_constraint() -> None:
    bind = op.get_bind()
    values = (
        "'received', 'validating', 'extracting', 'extracted', 'normalized', "
        "'pending_review', 'approved', 'rejected', 'failed', 'included_in_comparison'"
    )
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("quotes", recreate="always") as batch:
            batch.drop_constraint("ck_quotes_valid_quote_status", type_="check")
            batch.create_check_constraint("valid_quote_status", f"status IN ({values})")
    else:
        op.drop_constraint("ck_quotes_valid_quote_status", "quotes", type_="check")
        op.create_check_constraint("valid_quote_status", "quotes", f"status IN ({values})")


def upgrade() -> None:
    with op.batch_alter_table("quotes") as batch:
        batch.add_column(sa.Column("rfq_request_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("currency", sa.String(length=3), nullable=True))
        batch.add_column(sa.Column("subtotal_amount", sa.Numeric(24, 6), nullable=True))
        batch.add_column(sa.Column("tax_amount", sa.Numeric(24, 6), nullable=True))
        batch.add_column(sa.Column("total_amount", sa.Numeric(24, 6), nullable=True))
        batch.add_column(sa.Column("delivery_time_days", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("commercial_terms", sa.Text(), nullable=True))
        batch.add_column(sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("received_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("approved_extraction_run_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_quotes_rfq_request_id_rfq_requests", "rfq_requests", ["rfq_request_id"], ["id"], ondelete="SET NULL"
        )
        batch.create_index("ix_quotes_rfq_request_id", ["rfq_request_id"])
    op.execute(sa.text("UPDATE quotes SET received_at = created_at WHERE received_at IS NULL"))
    with op.batch_alter_table("quotes") as batch:
        batch.alter_column("received_at", nullable=False)
    _replace_quote_status_constraint()

    with op.batch_alter_table("quote_extraction_runs") as batch:
        batch.add_column(sa.Column("entity_type", sa.String(length=50), nullable=True))
        batch.add_column(sa.Column("provider", sa.String(length=100), nullable=True))
        batch.add_column(sa.Column("duration_ms", sa.Integer(), nullable=True))
    op.execute(sa.text("UPDATE quote_extraction_runs SET entity_type='quote', provider='openai' WHERE entity_type IS NULL OR provider IS NULL"))
    with op.batch_alter_table("quote_extraction_runs") as batch:
        batch.alter_column("entity_type", nullable=False)
        batch.alter_column("provider", nullable=False)

    op.create_table(
        "quote_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("quote_id", sa.Uuid(), nullable=False),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column("original_file_name", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=255), nullable=False),
        sa.Column("document_type", sa.String(length=50), nullable=False),
        sa.Column("processing_status", sa.String(length=30), nullable=False),
        sa.Column("file_hash", sa.String(length=64), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("extractor_name", sa.String(length=255), nullable=True),
        sa.Column("extractor_version", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["quote_id"], ["quotes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("quote_id", "file_hash", name="uq_quote_documents_quote_hash"),
    )
    op.create_index("ix_quote_documents_quote_id", "quote_documents", ["quote_id"])
    op.create_index("ix_quote_documents_status", "quote_documents", ["processing_status"])
    op.execute(sa.text("""
        INSERT INTO quote_documents (id, quote_id, storage_key, original_file_name, mime_type, document_type, processing_status, file_hash, file_size, created_at)
        SELECT id, id, storage_key, original_file_name, mime_type, 'supplier_quote',
               CASE WHEN status IN ('extracted','normalized','pending_review','approved','included_in_comparison') THEN 'extracted' ELSE 'stored' END,
               file_hash, file_size, created_at
        FROM quotes
    """))

    with op.batch_alter_table("quote_items") as batch:
        batch.add_column(sa.Column("extraction_run_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("description", sa.Text(), nullable=True))
        batch.add_column(sa.Column("unit", sa.String(length=50), nullable=True))
        batch.add_column(sa.Column("compliance_status", sa.String(length=30), nullable=True))
        batch.add_column(sa.Column("match_status", sa.String(length=30), nullable=True))
        batch.add_column(sa.Column("match_score", sa.Float(), nullable=True))
        batch.add_column(sa.Column("match_reason", sa.Text(), nullable=True))
        batch.add_column(sa.Column("quoted_specifications", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("source_evidence_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("warnings", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("original_extracted", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("is_current", sa.Boolean(), nullable=True))
        batch.add_column(sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_foreign_key(
            "fk_quote_items_extraction_run", "quote_extraction_runs", ["extraction_run_id"], ["id"], ondelete="SET NULL"
        )
    op.execute(sa.text("""
        UPDATE quote_items SET
          compliance_status = CASE WHEN technical_compliance IS TRUE THEN 'compliant' WHEN technical_compliance IS FALSE THEN 'non_compliant' ELSE 'unknown' END,
          match_status = CASE WHEN catalog_product_id IS NOT NULL THEN 'matched' ELSE 'unmatched' END,
          match_score = CASE WHEN catalog_product_id IS NOT NULL THEN 1.0 ELSE 0.0 END,
          quoted_specifications = '{}', warnings = '[]', original_extracted = '{}', is_current = TRUE, updated_at = created_at
    """))
    with op.batch_alter_table("quote_items") as batch:
        for column in ("compliance_status", "match_status", "match_score", "quoted_specifications", "warnings", "original_extracted", "is_current", "updated_at"):
            batch.alter_column(column, nullable=False)
        batch.create_index("ix_quote_items_run_current", ["extraction_run_id", "is_current"])

    op.create_table(
        "quote_evidence_references",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("quote_item_id", sa.Uuid(), nullable=True),
        sa.Column("quote_document_id", sa.Uuid(), nullable=False),
        sa.Column("extraction_run_id", sa.Uuid(), nullable=False),
        sa.Column("field_name", sa.String(length=100), nullable=False),
        sa.Column("location_type", sa.String(length=20), nullable=False),
        sa.Column("location_label", sa.String(length=255), nullable=False),
        sa.Column("fragment", sa.Text(), nullable=False),
        sa.Column("method", sa.String(length=255), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["quote_item_id"], ["quote_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["quote_document_id"], ["quote_documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["extraction_run_id"], ["quote_extraction_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_quote_evidence_item", "quote_evidence_references", ["quote_item_id"])
    op.create_index("ix_quote_evidence_document", "quote_evidence_references", ["quote_document_id"])

    op.create_table(
        "quote_item_revisions",
        sa.Column("id", sa.Uuid(), nullable=False), sa.Column("quote_item_id", sa.Uuid(), nullable=False),
        sa.Column("changed_by_user_id", sa.Uuid(), nullable=False), sa.Column("before", sa.JSON(), nullable=False),
        sa.Column("after", sa.JSON(), nullable=False), sa.Column("changed_fields", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["quote_item_id"], ["quote_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["changed_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_quote_item_revisions_item", "quote_item_revisions", ["quote_item_id"])

    op.create_table(
        "quote_task_records",
        sa.Column("id", sa.Uuid(), nullable=False), sa.Column("quote_id", sa.Uuid(), nullable=False),
        sa.Column("correlation_id", sa.String(length=255), nullable=False), sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("queued_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True), sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_type", sa.String(length=255), nullable=True), sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["quote_id"], ["quotes.id"], ondelete="CASCADE"), sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("correlation_id", name="uq_quote_task_correlation"),
    )
    op.create_index("ix_quote_tasks_quote", "quote_task_records", ["quote_id"])


def downgrade() -> None:
    op.drop_index("ix_quote_tasks_quote", table_name="quote_task_records")
    op.drop_table("quote_task_records")
    op.drop_index("ix_quote_item_revisions_item", table_name="quote_item_revisions")
    op.drop_table("quote_item_revisions")
    op.drop_index("ix_quote_evidence_document", table_name="quote_evidence_references")
    op.drop_index("ix_quote_evidence_item", table_name="quote_evidence_references")
    op.drop_table("quote_evidence_references")
    with op.batch_alter_table("quote_items") as batch:
        batch.drop_index("ix_quote_items_run_current")
        batch.drop_constraint("fk_quote_items_extraction_run", type_="foreignkey")
        for column in ("updated_at", "is_current", "original_extracted", "warnings", "source_evidence_id", "quoted_specifications", "match_reason", "match_score", "match_status", "compliance_status", "unit", "description", "extraction_run_id"):
            batch.drop_column(column)
    op.drop_index("ix_quote_documents_status", table_name="quote_documents")
    op.drop_index("ix_quote_documents_quote_id", table_name="quote_documents")
    op.drop_table("quote_documents")
    with op.batch_alter_table("quote_extraction_runs") as batch:
        batch.drop_column("duration_ms"); batch.drop_column("provider"); batch.drop_column("entity_type")
    # Restore legacy status check before removing added quote columns.
    bind = op.get_bind()
    legacy = "'received', 'validating', 'extracting', 'extracted', 'normalized', 'pending_review', 'approved', 'rejected', 'included_in_comparison'"
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("quotes", recreate="always") as batch:
            batch.drop_constraint("ck_quotes_valid_quote_status", type_="check")
            batch.create_check_constraint("valid_quote_status", f"status IN ({legacy})")
    else:
        op.drop_constraint("ck_quotes_valid_quote_status", "quotes", type_="check")
        op.create_check_constraint("valid_quote_status", "quotes", f"status IN ({legacy})")
    with op.batch_alter_table("quotes") as batch:
        batch.drop_index("ix_quotes_rfq_request_id")
        batch.drop_constraint("fk_quotes_rfq_request_id_rfq_requests", type_="foreignkey")
        for column in ("approved_extraction_run_id", "received_at", "valid_until", "commercial_terms", "delivery_time_days", "total_amount", "tax_amount", "subtotal_amount", "currency", "rfq_request_id"):
            batch.drop_column(column)
