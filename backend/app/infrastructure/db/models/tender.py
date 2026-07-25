from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.infrastructure.db.base import Base

if TYPE_CHECKING:
    from app.infrastructure.db.models.document_processing import ExtractionRunModel
    from app.infrastructure.db.models.user import UserModel


class TenderModel(Base):
    __tablename__ = "tenders"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'documents_pending', 'documents_processing', "
            "'catalog_review', 'cancelled', 'closed')",
            name="valid_tender_status",
        ),
        Index("ix_tenders_created_by_user_id", "created_by_user_id"),
        Index("ix_tenders_status", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_by: Mapped[UserModel] = relationship(back_populates="tenders")
    documents: Mapped[list[TenderDocumentModel]] = relationship(
        back_populates="tender",
        cascade="all, delete-orphan",
        order_by="TenderDocumentModel.created_at",
    )


class TenderDocumentModel(Base):
    __tablename__ = "tender_documents"
    __table_args__ = (
        CheckConstraint("file_size > 0", name="positive_file_size"),
        CheckConstraint(
            "processing_status IN ('uploaded', 'queued', 'processing', 'text_extracted', "
            "'ready_for_ai', 'needs_ocr', 'failed', 'deleted', 'rejected')",
            name="valid_document_status",
        ),
        UniqueConstraint("tender_id", "file_hash", name="uq_tender_documents_tender_file_hash"),
        Index("ix_tender_documents_tender_id", "tender_id"),
        Index("ix_tender_documents_uploaded_by_user_id", "uploaded_by_user_id"),
        Index("ix_tender_documents_file_hash", "file_hash"),
        Index("ix_tender_documents_deleted_at", "deleted_at"),
        Index("ix_tender_documents_processing_status", "processing_status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tender_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("tenders.id", ondelete="CASCADE"), nullable=False
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    document_type: Mapped[str] = mapped_column(String(50), nullable=False)
    processing_status: Mapped[str] = mapped_column(String(50), nullable=False)
    requires_ocr: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    uploaded_by_user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    processing_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_processing_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    tender: Mapped[TenderModel] = relationship(back_populates="documents")
    uploaded_by: Mapped[UserModel] = relationship(back_populates="uploaded_documents")
    extraction_runs: Mapped[list[ExtractionRunModel]] = relationship(
        cascade="all, delete-orphan",
        order_by="ExtractionRunModel.created_at",
    )
