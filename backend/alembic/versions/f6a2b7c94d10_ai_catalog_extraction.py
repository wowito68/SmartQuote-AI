"""add AI catalog extraction and review

Revision ID: f6a2b7c94d10
Revises: e5f1a9c73b20
Create Date: 2026-07-25 15:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f6a2b7c94d10"
down_revision: str | None = "e5f1a9c73b20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_extraction_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tender_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("prompt_version", sa.String(length=50), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("temperature", sa.Float(), nullable=False),
        sa.Column("schema_version", sa.String(length=50), nullable=False),
        sa.Column("schema_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("provider_response_id", sa.String(length=255), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "estimated_cost_usd",
            sa.Numeric(precision=18, scale=6),
            nullable=False,
            server_default="0",
        ),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("products_detected", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("invalid_json_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("raw_response", sa.JSON(), nullable=True),
        sa.Column("validation_errors", sa.JSON(), nullable=False),
        sa.Column("error_type", sa.String(length=255), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("reused_from_run_id", sa.Uuid(), nullable=True),
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
            name=op.f("ck_ai_extraction_runs_valid_ai_extraction_run_status"),
        ),
        sa.ForeignKeyConstraint(["document_id"], ["tender_documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["reused_from_run_id"], ["ai_extraction_runs.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["tender_id"], ["tenders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_id", "idempotency_key", name="uq_ai_runs_document_idempotency"
        ),
    )
    op.create_index("ix_ai_runs_tender_id", "ai_extraction_runs", ["tender_id"])
    op.create_index("ix_ai_runs_document_id", "ai_extraction_runs", ["document_id"])
    op.create_index("ix_ai_runs_status", "ai_extraction_runs", ["status"])

    op.create_table(
        "catalog_products",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tender_id", sa.Uuid(), nullable=False),
        sa.Column("ai_extraction_run_id", sa.Uuid(), nullable=False),
        sa.Column("source_document_id", sa.Uuid(), nullable=False),
        sa.Column("original_payload", sa.JSON(), nullable=False),
        sa.Column("item_number", sa.String(length=255), nullable=True),
        sa.Column("name", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("quantity", sa.Numeric(precision=24, scale=6), nullable=True),
        sa.Column("unit", sa.String(length=100), nullable=True),
        sa.Column("category", sa.String(length=255), nullable=True),
        sa.Column("specifications", sa.JSON(), nullable=False),
        sa.Column("observations", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("duplicate_of_product_id", sa.Uuid(), nullable=True),
        sa.Column("manual_edit_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reviewed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
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
            "status IN ('candidate', 'normalized', 'pending_review', 'approved', 'rejected')",
            name=op.f("ck_catalog_products_valid_catalog_product_status"),
        ),
        sa.ForeignKeyConstraint(
            ["ai_extraction_run_id"], ["ai_extraction_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["duplicate_of_product_id"], ["catalog_products.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["source_document_id"], ["tender_documents.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["tender_id"], ["tenders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_catalog_products_tender_id", "catalog_products", ["tender_id"])
    op.create_index("ix_catalog_products_ai_run_id", "catalog_products", ["ai_extraction_run_id"])
    op.create_index("ix_catalog_products_status", "catalog_products", ["status"])
    op.create_index(
        "ix_catalog_products_source_document_id", "catalog_products", ["source_document_id"]
    )

    op.create_table(
        "catalog_product_revisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("changed_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("before_payload", sa.JSON(), nullable=False),
        sa.Column("after_payload", sa.JSON(), nullable=False),
        sa.Column("changed_fields", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["changed_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["product_id"], ["catalog_products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_catalog_revisions_product_id", "catalog_product_revisions", ["product_id"]
    )

    op.create_table(
        "extracted_evidence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("ai_extraction_run_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("text_fragment", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("prompt_version", sa.String(length=50), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["ai_extraction_run_id"], ["ai_extraction_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["document_id"], ["tender_documents.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["product_id"], ["catalog_products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_extracted_evidence_product_id", "extracted_evidence", ["product_id"])
    op.create_index("ix_extracted_evidence_document_id", "extracted_evidence", ["document_id"])
    op.create_index(
        "ix_extracted_evidence_ai_run_id",
        "extracted_evidence",
        ["ai_extraction_run_id"],
    )

    op.create_table(
        "evidence_references",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("evidence_id", sa.Uuid(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("x0", sa.Float(), nullable=True),
        sa.Column("y0", sa.Float(), nullable=True),
        sa.Column("x1", sa.Float(), nullable=True),
        sa.Column("y1", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["evidence_id"], ["extracted_evidence.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_evidence_references_evidence_id", "evidence_references", ["evidence_id"])

    op.create_table(
        "catalog_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tender_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("approved_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("products", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tender_id"], ["tenders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tender_id", "version", name="uq_catalog_snapshots_tender_version"),
    )
    op.create_index("ix_catalog_snapshots_tender_id", "catalog_snapshots", ["tender_id"])


def downgrade() -> None:
    op.drop_index("ix_catalog_snapshots_tender_id", table_name="catalog_snapshots")
    op.drop_table("catalog_snapshots")
    op.drop_index("ix_evidence_references_evidence_id", table_name="evidence_references")
    op.drop_table("evidence_references")
    op.drop_index("ix_extracted_evidence_ai_run_id", table_name="extracted_evidence")
    op.drop_index("ix_extracted_evidence_document_id", table_name="extracted_evidence")
    op.drop_index("ix_extracted_evidence_product_id", table_name="extracted_evidence")
    op.drop_table("extracted_evidence")
    op.drop_index("ix_catalog_revisions_product_id", table_name="catalog_product_revisions")
    op.drop_table("catalog_product_revisions")
    op.drop_index("ix_catalog_products_source_document_id", table_name="catalog_products")
    op.drop_index("ix_catalog_products_status", table_name="catalog_products")
    op.drop_index("ix_catalog_products_ai_run_id", table_name="catalog_products")
    op.drop_index("ix_catalog_products_tender_id", table_name="catalog_products")
    op.drop_table("catalog_products")
    op.drop_index("ix_ai_runs_status", table_name="ai_extraction_runs")
    op.drop_index("ix_ai_runs_document_id", table_name="ai_extraction_runs")
    op.drop_index("ix_ai_runs_tender_id", table_name="ai_extraction_runs")
    op.drop_table("ai_extraction_runs")
