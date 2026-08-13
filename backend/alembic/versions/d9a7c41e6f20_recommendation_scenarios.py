"""add explainable recommendation scenarios

Revision ID: d9a7c41e6f20
Revises: c8f3a05d6e94
Create Date: 2026-08-13 14:30:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d9a7c41e6f20"
down_revision: str | None = "c8f3a05d6e94"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "recommendations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("comparison_id", sa.Uuid(), nullable=False),
        sa.Column("tender_id", sa.Uuid(), nullable=False),
        sa.Column("recommendation_key", sa.String(length=64), nullable=False),
        sa.Column("policy_version", sa.String(length=50), nullable=False),
        sa.Column("weights", sa.JSON(), nullable=False),
        sa.Column("generated_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("candidates", sa.JSON(), nullable=False),
        sa.Column("recommended_supplier_id", sa.Uuid(), nullable=True),
        sa.Column("recommended_supplier_name", sa.String(length=500), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column(
            "human_review_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status IN ('ready', 'withheld')",
            name="valid_recommendation_status",
        ),
        sa.CheckConstraint(
            "human_review_required = true",
            name="recommendation_requires_human_review",
        ),
        sa.ForeignKeyConstraint(
            ["comparison_id"],
            ["comparisons.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tender_id"],
            ["tenders.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["generated_by_user_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["recommended_supplier_id"],
            ["suppliers.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "comparison_id",
            "recommendation_key",
            name="uq_recommendations_comparison_key",
        ),
    )
    op.create_index(
        "ix_recommendations_comparison_id",
        "recommendations",
        ["comparison_id"],
        unique=False,
    )
    op.create_index(
        "ix_recommendations_tender_id",
        "recommendations",
        ["tender_id"],
        unique=False,
    )
    op.create_index(
        "ix_recommendations_status",
        "recommendations",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_recommendations_status", table_name="recommendations")
    op.drop_index("ix_recommendations_tender_id", table_name="recommendations")
    op.drop_index("ix_recommendations_comparison_id", table_name="recommendations")
    op.drop_table("recommendations")
