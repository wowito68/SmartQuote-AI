"""create initial core tables

Revision ID: 9f6e762a7fc6
Revises:
Create Date: 2026-07-24 16:20:23.228841

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9f6e762a7fc6"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    op.create_table(
        "tenders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ("
            "'draft', "
            "'documents_pending', "
            "'documents_processing', "
            "'catalog_review', "
            "'cancelled', "
            "'closed'"
            ")",
            name=op.f("ck_tenders_valid_tender_status"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_tenders_created_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tenders")),
    )
    op.create_index(
        "ix_tenders_created_by_user_id",
        "tenders",
        ["created_by_user_id"],
        unique=False,
    )
    op.create_index("ix_tenders_status", "tenders", ["status"], unique=False)

    op.create_table(
        "tender_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tender_id", sa.Uuid(), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("file_path", sa.String(length=1024), nullable=False),
        sa.Column("mime_type", sa.String(length=255), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("file_hash", sa.String(length=64), nullable=False),
        sa.Column("document_type", sa.String(length=50), nullable=False),
        sa.Column("processing_status", sa.String(length=50), nullable=False),
        sa.Column("requires_ocr", sa.Boolean(), nullable=False),
        sa.Column("uploaded_by_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "processing_status IN ("
            "'uploaded', "
            "'validating', "
            "'valid', "
            "'stored', "
            "'extracting_text', "
            "'text_extracted', "
            "'needs_ocr', "
            "'processed', "
            "'rejected', "
            "'failed'"
            ")",
            name=op.f("ck_tender_documents_valid_document_status"),
        ),
        sa.CheckConstraint(
            "file_size > 0",
            name=op.f("ck_tender_documents_positive_file_size"),
        ),
        sa.ForeignKeyConstraint(
            ["tender_id"],
            ["tenders.id"],
            name=op.f("fk_tender_documents_tender_id_tenders"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by_user_id"],
            ["users.id"],
            name=op.f("fk_tender_documents_uploaded_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tender_documents")),
        sa.UniqueConstraint(
            "tender_id",
            "file_hash",
            name="uq_tender_documents_tender_file_hash",
        ),
    )
    op.create_index(
        "ix_tender_documents_file_hash",
        "tender_documents",
        ["file_hash"],
        unique=False,
    )
    op.create_index(
        "ix_tender_documents_tender_id",
        "tender_documents",
        ["tender_id"],
        unique=False,
    )
    op.create_index(
        "ix_tender_documents_uploaded_by_user_id",
        "tender_documents",
        ["uploaded_by_user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_tender_documents_uploaded_by_user_id", table_name="tender_documents")
    op.drop_index("ix_tender_documents_tender_id", table_name="tender_documents")
    op.drop_index("ix_tender_documents_file_hash", table_name="tender_documents")
    op.drop_table("tender_documents")
    op.drop_index("ix_tenders_status", table_name="tenders")
    op.drop_index("ix_tenders_created_by_user_id", table_name="tenders")
    op.drop_table("tenders")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")

