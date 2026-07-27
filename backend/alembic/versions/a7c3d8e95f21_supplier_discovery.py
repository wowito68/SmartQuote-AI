"""add supplier discovery and review

Revision ID: a7c3d8e95f21
Revises: f6a2b7c94d10
Create Date: 2026-07-27 10:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a7c3d8e95f21"
down_revision: str | None = "f6a2b7c94d10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "supplier_discovery_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tender_id", sa.Uuid(), nullable=False),
        sa.Column("catalog_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("search_provider", sa.String(length=255), nullable=False),
        sa.Column("search_provider_version", sa.String(length=100), nullable=False),
        sa.Column("search_configuration", sa.JSON(), nullable=False),
        sa.Column("matching_algorithm_version", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("current_stage", sa.String(length=100), nullable=False),
        sa.Column("raw_candidates", sa.JSON(), nullable=False),
        sa.Column("processed_candidates", sa.JSON(), nullable=False),
        sa.Column("suppliers_found", sa.Integer(), server_default="0", nullable=False),
        sa.Column("duplicates_detected", sa.Integer(), server_default="0", nullable=False),
        sa.Column("contacts_found", sa.Integer(), server_default="0", nullable=False),
        sa.Column("provider_errors", sa.JSON(), nullable=False),
        sa.Column("search_duration_ms", sa.Integer(), nullable=True),
        sa.Column("matching_duration_ms", sa.Integer(), nullable=True),
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
            name=op.f("ck_supplier_discovery_runs_valid_supplier_discovery_run_status"),
        ),
        sa.ForeignKeyConstraint(
            ["catalog_snapshot_id"], ["catalog_snapshots.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["reused_from_run_id"], ["supplier_discovery_runs.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["tender_id"], ["tenders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tender_id", "idempotency_key", name="uq_supplier_runs_tender_idempotency"
        ),
    )
    op.create_index("ix_supplier_runs_tender_id", "supplier_discovery_runs", ["tender_id"])
    op.create_index("ix_supplier_runs_status", "supplier_discovery_runs", ["status"])

    op.create_table(
        "suppliers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("legal_name", sa.String(length=500), nullable=True),
        sa.Column("trade_name", sa.String(length=500), nullable=True),
        sa.Column("website", sa.String(length=2000), nullable=True),
        sa.Column("normalized_domain", sa.String(length=500), nullable=True),
        sa.Column("category", sa.String(length=255), nullable=True),
        sa.Column("country", sa.String(length=100), nullable=True),
        sa.Column("city", sa.String(length=255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("merged_into_supplier_id", sa.Uuid(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["merged_into_supplier_id"], ["suppliers.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_suppliers_normalized_domain", "suppliers", ["normalized_domain"])
    op.create_index("ix_suppliers_legal_name", "suppliers", ["legal_name"])
    op.create_index("ix_suppliers_trade_name", "suppliers", ["trade_name"])

    op.create_table(
        "supplier_contacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("supplier_id", sa.Uuid(), nullable=False),
        sa.Column("contact_type", sa.String(length=30), nullable=False),
        sa.Column("value", sa.String(length=2000), nullable=False),
        sa.Column("identity_key", sa.String(length=2100), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("source_url", sa.String(length=2000), nullable=False),
        sa.Column("contact_name", sa.String(length=255), nullable=True),
        sa.Column("role", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "contact_type IN ('email', 'phone', 'whatsapp', 'contact_form')",
            name=op.f("ck_supplier_contacts_valid_supplier_contact_type"),
        ),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "supplier_id", "identity_key", name="uq_supplier_contacts_identity"
        ),
    )
    op.create_index("ix_supplier_contacts_supplier_id", "supplier_contacts", ["supplier_id"])

    op.create_table(
        "supplier_sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("supplier_id", sa.Uuid(), nullable=False),
        sa.Column("provider_name", sa.String(length=255), nullable=False),
        sa.Column("source_type", sa.String(length=100), nullable=False),
        sa.Column("source_url", sa.String(length=2000), nullable=False),
        sa.Column("source_title", sa.String(length=500), nullable=True),
        sa.Column("excerpt", sa.Text(), nullable=True),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("supplier_id", "source_url", name="uq_supplier_sources_url"),
    )
    op.create_index("ix_supplier_sources_supplier_id", "supplier_sources", ["supplier_id"])

    op.create_table(
        "tender_suppliers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tender_id", sa.Uuid(), nullable=False),
        sa.Column("supplier_id", sa.Uuid(), nullable=False),
        sa.Column("discovery_run_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("is_manual", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("reviewed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("merged_into_tender_supplier_id", sa.Uuid(), nullable=True),
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
            "status IN ('candidate', 'contacts_found', 'pending_review', "
            "'approved', 'rejected', 'merged')",
            name=op.f("ck_tender_suppliers_valid_tender_supplier_status"),
        ),
        sa.ForeignKeyConstraint(
            ["discovery_run_id"], ["supplier_discovery_runs.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["merged_into_tender_supplier_id"], ["tender_suppliers.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tender_id"], ["tenders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tender_id", "supplier_id", name="uq_tender_suppliers_master"),
    )
    op.create_index("ix_tender_suppliers_tender_id", "tender_suppliers", ["tender_id"])
    op.create_index("ix_tender_suppliers_supplier_id", "tender_suppliers", ["supplier_id"])
    op.create_index("ix_tender_suppliers_status", "tender_suppliers", ["status"])

    op.create_table(
        "product_supplier_matches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tender_supplier_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("components", sa.JSON(), nullable=False),
        sa.Column("reasons", sa.JSON(), nullable=False),
        sa.Column("algorithm_version", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["product_id"], ["catalog_products.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["tender_supplier_id"], ["tender_suppliers.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tender_supplier_id", "product_id", name="uq_product_supplier_match"
        ),
    )
    op.create_index(
        "ix_product_supplier_matches_tender_supplier",
        "product_supplier_matches",
        ["tender_supplier_id"],
    )
    op.create_index(
        "ix_product_supplier_matches_product", "product_supplier_matches", ["product_id"]
    )

    op.create_table(
        "supplier_merge_suggestions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_supplier_id", sa.Uuid(), nullable=False),
        sa.Column("target_supplier_id", sa.Uuid(), nullable=False),
        sa.Column("discovery_run_id", sa.Uuid(), nullable=True),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("signals", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("reviewed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'rejected')",
            name=op.f("ck_supplier_merge_suggestions_valid_supplier_merge_suggestion_status"),
        ),
        sa.ForeignKeyConstraint(
            ["discovery_run_id"], ["supplier_discovery_runs.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["source_supplier_id"], ["suppliers.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["target_supplier_id"], ["suppliers.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_supplier_id",
            "target_supplier_id",
            "discovery_run_id",
            name="uq_supplier_merge_suggestion_pair_run",
        ),
    )
    op.create_index(
        "ix_supplier_merge_source", "supplier_merge_suggestions", ["source_supplier_id"]
    )
    op.create_index(
        "ix_supplier_merge_target", "supplier_merge_suggestions", ["target_supplier_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_supplier_merge_target", table_name="supplier_merge_suggestions")
    op.drop_index("ix_supplier_merge_source", table_name="supplier_merge_suggestions")
    op.drop_table("supplier_merge_suggestions")
    op.drop_index("ix_product_supplier_matches_product", table_name="product_supplier_matches")
    op.drop_index(
        "ix_product_supplier_matches_tender_supplier",
        table_name="product_supplier_matches",
    )
    op.drop_table("product_supplier_matches")
    op.drop_index("ix_tender_suppliers_status", table_name="tender_suppliers")
    op.drop_index("ix_tender_suppliers_supplier_id", table_name="tender_suppliers")
    op.drop_index("ix_tender_suppliers_tender_id", table_name="tender_suppliers")
    op.drop_table("tender_suppliers")
    op.drop_index("ix_supplier_sources_supplier_id", table_name="supplier_sources")
    op.drop_table("supplier_sources")
    op.drop_index("ix_supplier_contacts_supplier_id", table_name="supplier_contacts")
    op.drop_table("supplier_contacts")
    op.drop_index("ix_suppliers_trade_name", table_name="suppliers")
    op.drop_index("ix_suppliers_legal_name", table_name="suppliers")
    op.drop_index("ix_suppliers_normalized_domain", table_name="suppliers")
    op.drop_table("suppliers")
    op.drop_index("ix_supplier_runs_status", table_name="supplier_discovery_runs")
    op.drop_index("ix_supplier_runs_tender_id", table_name="supplier_discovery_runs")
    op.drop_table("supplier_discovery_runs")
