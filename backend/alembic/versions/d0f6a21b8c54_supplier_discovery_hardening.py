"""harden supplier discovery traceability

Revision ID: d0f6a21b8c54
Revises: c9e5f10a7b43
Create Date: 2026-08-08 13:55:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d0f6a21b8c54"
down_revision: str | None = "c9e5f10a7b43"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("supplier_sources") as batch_op:
        batch_op.drop_constraint("uq_supplier_sources_url", type_="unique")
        batch_op.add_column(sa.Column("discovery_run_id", sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column("product_id", sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column("query", sa.String(length=2000), nullable=True))
        batch_op.add_column(sa.Column("source_name", sa.String(length=500), nullable=True))
        batch_op.add_column(
            sa.Column("metadata", sa.JSON(), server_default=sa.text("'{}'"), nullable=False)
        )
        batch_op.create_foreign_key(
            "fk_supplier_sources_discovery_run",
            "supplier_discovery_runs",
            ["discovery_run_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_supplier_sources_product",
            "catalog_products",
            ["product_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index(
        "ix_supplier_sources_discovery_run_id", "supplier_sources", ["discovery_run_id"]
    )
    op.create_index("ix_supplier_sources_product_id", "supplier_sources", ["product_id"])

    with op.batch_alter_table("product_supplier_matches") as batch_op:
        batch_op.add_column(
            sa.Column("match_status", sa.String(length=20), server_default="candidate", nullable=False)
        )
        batch_op.add_column(sa.Column("source_url", sa.String(length=2000), nullable=True))
        batch_op.add_column(sa.Column("reason", sa.Text(), nullable=True))
        batch_op.create_check_constraint(
            "valid_product_supplier_match_status",
            "match_status IN ('candidate', 'confirmed', 'rejected')",
        )


def downgrade() -> None:
    with op.batch_alter_table("product_supplier_matches") as batch_op:
        batch_op.drop_constraint("valid_product_supplier_match_status", type_="check")
        batch_op.drop_column("reason")
        batch_op.drop_column("source_url")
        batch_op.drop_column("match_status")

    op.drop_index("ix_supplier_sources_product_id", table_name="supplier_sources")
    op.drop_index("ix_supplier_sources_discovery_run_id", table_name="supplier_sources")
    with op.batch_alter_table("supplier_sources") as batch_op:
        batch_op.drop_constraint("fk_supplier_sources_product", type_="foreignkey")
        batch_op.drop_constraint("fk_supplier_sources_discovery_run", type_="foreignkey")
        batch_op.drop_column("metadata")
        batch_op.drop_column("source_name")
        batch_op.drop_column("query")
        batch_op.drop_column("product_id")
        batch_op.drop_column("discovery_run_id")
        batch_op.create_unique_constraint(
            "uq_supplier_sources_url", ["supplier_id", "source_url"]
        )
