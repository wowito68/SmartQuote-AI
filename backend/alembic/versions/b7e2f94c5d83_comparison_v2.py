"""add deterministic comparison v2

Revision ID: b7e2f94c5d83
Revises: a6d1e83f4b72
Create Date: 2026-08-11 10:15:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7e2f94c5d83"
down_revision: str | None = "a6d1e83f4b72"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "comparisons",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tender_id", sa.Uuid(), nullable=False),
        sa.Column("catalog_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("catalog_version", sa.Integer(), nullable=False),
        sa.Column("quotes_version", sa.String(length=64), nullable=False),
        sa.Column("comparison_version", sa.String(length=50), nullable=False),
        sa.Column("comparison_key", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("source_quote_ids", sa.JSON(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('draft', 'building', 'ready', 'invalid', 'archived')",
            name="valid_comparison_status",
        ),
        sa.ForeignKeyConstraint(["tender_id"], ["tenders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["catalog_snapshot_id"], ["catalog_snapshots.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tender_id",
            "comparison_key",
            name="uq_comparisons_tender_key",
        ),
    )
    op.create_index("ix_comparisons_tender_id", "comparisons", ["tender_id"])
    op.create_index("ix_comparisons_status", "comparisons", ["status"])

    op.create_table(
        "comparison_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("comparison_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("requested_product_name", sa.String(length=500), nullable=False),
        sa.Column("requested_quantity", sa.Numeric(precision=24, scale=6), nullable=True),
        sa.Column("requested_unit", sa.String(length=100), nullable=True),
        sa.Column("monetary_status", sa.String(length=30), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "monetary_status IN ('comparable', 'requires_normalization', 'insufficient_data')",
            name="valid_comparison_monetary_status",
        ),
        sa.ForeignKeyConstraint(
            ["comparison_id"], ["comparisons.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["product_id"], ["catalog_products.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "comparison_id",
            "product_id",
            name="uq_comparison_items_product",
        ),
    )
    op.create_index(
        "ix_comparison_items_comparison_id",
        "comparison_items",
        ["comparison_id"],
    )
    op.create_index(
        "ix_comparison_items_product_id",
        "comparison_items",
        ["product_id"],
    )

    op.create_table(
        "comparison_offers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("comparison_item_id", sa.Uuid(), nullable=False),
        sa.Column("supplier_id", sa.Uuid(), nullable=False),
        sa.Column("supplier_name", sa.String(length=500), nullable=False),
        sa.Column("quote_id", sa.Uuid(), nullable=True),
        sa.Column("quote_item_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("quoted_product_name", sa.String(length=500), nullable=True),
        sa.Column("brand", sa.String(length=255), nullable=True),
        sa.Column("model", sa.String(length=255), nullable=True),
        sa.Column("quoted_quantity", sa.Numeric(precision=24, scale=6), nullable=True),
        sa.Column("quoted_unit", sa.String(length=100), nullable=True),
        sa.Column("quantity_status", sa.String(length=30), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=24, scale=6), nullable=True),
        sa.Column("total_price", sa.Numeric(precision=24, scale=6), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("compliance_status", sa.String(length=30), nullable=False),
        sa.Column("delivery_days", sa.Integer(), nullable=True),
        sa.Column("delivery_original_text", sa.Text(), nullable=True),
        sa.Column("delivery_normalized", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("observations", sa.Text(), nullable=True),
        sa.Column("commercial_terms", sa.Text(), nullable=True),
        sa.Column("evidence_id", sa.Uuid(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('quoted', 'missing', 'invalid')",
            name="valid_comparison_offer_status",
        ),
        sa.CheckConstraint(
            "quantity_status IN ('matched', 'quantity_mismatch', 'unit_mismatch', 'unknown')",
            name="valid_comparison_quantity_status",
        ),
        sa.CheckConstraint(
            "compliance_status IN ('compliant', 'partially_compliant', 'non_compliant', 'unknown')",
            name="valid_comparison_compliance_status",
        ),
        sa.ForeignKeyConstraint(
            ["comparison_item_id"], ["comparison_items.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["supplier_id"], ["suppliers.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["quote_id"], ["quotes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["quote_item_id"], ["quote_items.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["evidence_id"], ["quote_evidence_references.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "comparison_item_id",
            "supplier_id",
            name="uq_comparison_offers_supplier",
        ),
    )
    op.create_index(
        "ix_comparison_offers_item_id",
        "comparison_offers",
        ["comparison_item_id"],
    )
    op.create_index(
        "ix_comparison_offers_supplier_id",
        "comparison_offers",
        ["supplier_id"],
    )
    op.create_index(
        "ix_comparison_offers_quote_id",
        "comparison_offers",
        ["quote_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_comparison_offers_quote_id", table_name="comparison_offers")
    op.drop_index("ix_comparison_offers_supplier_id", table_name="comparison_offers")
    op.drop_index("ix_comparison_offers_item_id", table_name="comparison_offers")
    op.drop_table("comparison_offers")
    op.drop_index("ix_comparison_items_product_id", table_name="comparison_items")
    op.drop_index("ix_comparison_items_comparison_id", table_name="comparison_items")
    op.drop_table("comparison_items")
    op.drop_index("ix_comparisons_status", table_name="comparisons")
    op.drop_index("ix_comparisons_tender_id", table_name="comparisons")
    op.drop_table("comparisons")
