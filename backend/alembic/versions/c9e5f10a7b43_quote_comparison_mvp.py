"""add quote analysis comparison and recommendation MVP

Revision ID: c9e5f10a7b43
Revises: b8d4e9f06a32
Create Date: 2026-08-08 12:45:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c9e5f10a7b43"
down_revision: str | None = "b8d4e9f06a32"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _replace_check_constraint(table: str, name: str, condition: str) -> None:
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table(table, recreate="always") as batch_op:
            batch_op.drop_constraint(name, type_="check")
            batch_op.create_check_constraint(name, condition)
        return
    op.drop_constraint(name, table, type_="check")
    op.create_check_constraint(name, table, condition)


def _expand_state_constraints() -> None:
    _replace_check_constraint(
        "tenders",
        "valid_tender_status",
        "status IN ('draft', 'documents_pending', 'documents_processing', 'catalog_review', "
        "'supplier_review', 'rfq_ready', 'waiting_quotes', 'quote_analysis', "
        "'comparison_ready', 'awarded', 'cancelled', 'closed')",
    )
    _replace_check_constraint(
        "catalog_products",
        "valid_catalog_product_status",
        "status IN ('candidate', 'normalized', 'pending_review', 'approved', 'rejected', "
        "'quoted', 'compared')",
    )
    _replace_check_constraint(
        "tender_suppliers",
        "valid_tender_supplier_status",
        "status IN ('candidate', 'contacts_found', 'pending_review', 'approved', 'rejected', "
        "'merged', 'contacted', 'responded', 'inactive')",
    )
    _replace_check_constraint(
        "rfq_requests",
        "valid_rfq_status",
        "status IN ('draft', 'pending_review', 'approved', 'queued', 'sending', 'sent', "
        "'delivered', 'responded', 'failed', 'cancelled')",
    )


def upgrade() -> None:
    _expand_state_constraints()

    op.create_table(
        "quotes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tender_id", sa.Uuid(), nullable=False),
        sa.Column("tender_supplier_id", sa.Uuid(), nullable=False),
        sa.Column("supplier_id", sa.Uuid(), nullable=False),
        sa.Column("original_file_name", sa.String(length=255), nullable=False),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column("mime_type", sa.String(length=255), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("file_hash", sa.String(length=64), nullable=False),
        sa.Column("uploaded_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("manual_edit_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("reviewed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('received', 'validating', 'extracting', 'extracted', 'normalized', "
            "'pending_review', 'approved', 'rejected', 'included_in_comparison')",
            name="valid_quote_status",
        ),
        sa.ForeignKeyConstraint(["tender_id"], ["tenders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["tender_supplier_id"], ["tender_suppliers.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["uploaded_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tender_id",
            "supplier_id",
            "file_hash",
            name="uq_quotes_tender_supplier_file_hash",
        ),
    )
    op.create_index("ix_quotes_tender_id", "quotes", ["tender_id"])
    op.create_index("ix_quotes_supplier_id", "quotes", ["supplier_id"])
    op.create_index("ix_quotes_status", "quotes", ["status"])

    op.create_table(
        "quote_extraction_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("quote_id", sa.Uuid(), nullable=False),
        sa.Column("tender_id", sa.Uuid(), nullable=False),
        sa.Column("supplier_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("extractor_version", sa.String(length=100), nullable=False),
        sa.Column("prompt_version", sa.String(length=50), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("schema_version", sa.String(length=50), nullable=False),
        sa.Column("schema_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("provider_response_id", sa.String(length=255), nullable=True),
        sa.Column("input_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("output_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "estimated_cost_usd",
            sa.Numeric(precision=18, scale=6),
            server_default="0",
            nullable=False,
        ),
        sa.Column("raw_response", sa.JSON(), nullable=True),
        sa.Column("error_type", sa.String(length=255), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed', 'reused')",
            name="valid_quote_extraction_run_status",
        ),
        sa.ForeignKeyConstraint(["quote_id"], ["quotes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tender_id"], ["tenders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("quote_id", "idempotency_key", name="uq_quote_runs_quote_idempotency"),
    )
    op.create_index("ix_quote_runs_quote_id", "quote_extraction_runs", ["quote_id"])
    op.create_index("ix_quote_runs_tender_id", "quote_extraction_runs", ["tender_id"])

    op.create_table(
        "quote_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("quote_id", sa.Uuid(), nullable=False),
        sa.Column("catalog_product_id", sa.Uuid(), nullable=True),
        sa.Column("product_name", sa.String(length=500), nullable=False),
        sa.Column("brand", sa.String(length=255), nullable=True),
        sa.Column("model", sa.String(length=255), nullable=True),
        sa.Column("quantity", sa.Numeric(precision=24, scale=6), nullable=True),
        sa.Column("unit_price", sa.Numeric(precision=24, scale=6), nullable=True),
        sa.Column("total_price", sa.Numeric(precision=24, scale=6), nullable=True),
        sa.Column("currency", sa.String(length=10), nullable=True),
        sa.Column("delivery_days", sa.Integer(), nullable=True),
        sa.Column("technical_compliance", sa.Boolean(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("source_page", sa.Integer(), nullable=True),
        sa.Column("evidence_fragment", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["quote_id"], ["quotes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["catalog_product_id"], ["catalog_products.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_quote_items_quote_id", "quote_items", ["quote_id"])
    op.create_index(
        "ix_quote_items_catalog_product_id", "quote_items", ["catalog_product_id"]
    )

    op.create_table(
        "comparison_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tender_id", sa.Uuid(), nullable=False),
        sa.Column("catalog_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("comparison_key", sa.String(length=64), nullable=False),
        sa.Column("approved_quotes_version", sa.String(length=64), nullable=False),
        sa.Column("scoring_config_version", sa.String(length=50), nullable=False),
        sa.Column("rows", sa.JSON(), nullable=False),
        sa.Column("recommendation", sa.JSON(), nullable=False),
        sa.Column("generated_by_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tender_id"], ["tenders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["catalog_snapshot_id"], ["catalog_snapshots.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["generated_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tender_id", "comparison_key", name="uq_comparison_tender_key"),
    )
    op.create_index("ix_comparison_runs_tender_id", "comparison_runs", ["tender_id"])


def downgrade() -> None:
    op.drop_index("ix_comparison_runs_tender_id", table_name="comparison_runs")
    op.drop_table("comparison_runs")
    op.drop_index("ix_quote_items_catalog_product_id", table_name="quote_items")
    op.drop_index("ix_quote_items_quote_id", table_name="quote_items")
    op.drop_table("quote_items")
    op.drop_index("ix_quote_runs_tender_id", table_name="quote_extraction_runs")
    op.drop_index("ix_quote_runs_quote_id", table_name="quote_extraction_runs")
    op.drop_table("quote_extraction_runs")
    op.drop_index("ix_quotes_status", table_name="quotes")
    op.drop_index("ix_quotes_supplier_id", table_name="quotes")
    op.drop_index("ix_quotes_tender_id", table_name="quotes")
    op.drop_table("quotes")

    _replace_check_constraint(
        "rfq_requests",
        "valid_rfq_status",
        "status IN ('draft', 'pending_review', 'approved', 'queued', 'sending', 'sent', "
        "'delivered', 'failed', 'cancelled')",
    )
    _replace_check_constraint(
        "tender_suppliers",
        "valid_tender_supplier_status",
        "status IN ('candidate', 'contacts_found', 'pending_review', 'approved', "
        "'rejected', 'merged')",
    )
    _replace_check_constraint(
        "catalog_products",
        "valid_catalog_product_status",
        "status IN ('candidate', 'normalized', 'pending_review', 'approved', 'rejected')",
    )
    _replace_check_constraint(
        "tenders",
        "valid_tender_status",
        "status IN ('draft', 'documents_pending', 'documents_processing', 'catalog_review', "
        "'cancelled', 'closed')",
    )
