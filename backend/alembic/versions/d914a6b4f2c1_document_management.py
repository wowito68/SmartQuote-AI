"""add document management lifecycle

Revision ID: d914a6b4f2c1
Revises: c842c17be491
Create Date: 2026-07-25 12:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d914a6b4f2c1"
down_revision: str | None = "c842c17be491"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_STATUS_CONSTRAINT = (
    "processing_status IN ('uploaded', 'validating', 'valid', 'stored', "
    "'extracting_text', 'text_extracted', 'needs_ocr', 'processed', "
    "'rejected', 'failed')"
)
NEW_STATUS_CONSTRAINT = "processing_status IN ('uploaded', 'deleted', 'rejected')"


def _replace_status_constraint(expression: str) -> None:
    recreate = "always" if op.get_bind().dialect.name == "sqlite" else "auto"
    with op.batch_alter_table("tender_documents", recreate=recreate) as batch_op:
        batch_op.drop_constraint(
            op.f("ck_tender_documents_valid_document_status"),
            type_="check",
        )
        batch_op.create_check_constraint("valid_document_status", expression)


def upgrade() -> None:
    op.execute(
        "UPDATE tender_documents SET processing_status = 'rejected' "
        "WHERE processing_status NOT IN ('uploaded', 'rejected')"
    )
    _replace_status_constraint(NEW_STATUS_CONSTRAINT)
    op.add_column(
        "tender_documents",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_tender_documents_deleted_at",
        "tender_documents",
        ["deleted_at"],
        unique=False,
    )


def downgrade() -> None:
    op.execute(
        "UPDATE tender_documents SET processing_status = 'rejected' "
        "WHERE processing_status = 'deleted'"
    )
    op.drop_index("ix_tender_documents_deleted_at", table_name="tender_documents")
    op.drop_column("tender_documents", "deleted_at")
    _replace_status_constraint(OLD_STATUS_CONSTRAINT)
