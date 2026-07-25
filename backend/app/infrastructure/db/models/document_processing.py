from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.infrastructure.db.base import Base


class ExtractionRunModel(Base):
    __tablename__ = "extraction_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'completed', 'failed', 'reused')",
            name="valid_extraction_run_status",
        ),
        UniqueConstraint(
            "document_id", "processing_key", name="uq_extraction_runs_document_processing_key"
        ),
        Index("ix_extraction_runs_document_id", "document_id"),
        Index("ix_extraction_runs_status", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    document_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("tender_documents.id", ondelete="CASCADE"), nullable=False
    )
    processing_key: Mapped[str] = mapped_column(String(64), nullable=False)
    extractor_name: Mapped[str] = mapped_column(String(100), nullable=False)
    extractor_version: Mapped[str] = mapped_column(String(100), nullable=False)
    configuration: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    pages_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    characters_extracted: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    error_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    reused_from_run_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("extraction_runs.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    pages: Mapped[list[DocumentPageModel]] = relationship(
        back_populates="extraction_run",
        cascade="all, delete-orphan",
        order_by="DocumentPageModel.page_number",
    )
    quality: Mapped[DocumentQualityModel | None] = relationship(
        back_populates="extraction_run", cascade="all, delete-orphan", uselist=False
    )


class DocumentPageModel(Base):
    __tablename__ = "document_pages"
    __table_args__ = (
        UniqueConstraint("extraction_run_id", "page_number", name="uq_document_pages_run_page"),
        CheckConstraint("page_number > 0", name="positive_document_page_number"),
        Index("ix_document_pages_document_id", "document_id"),
        Index("ix_document_pages_extraction_run_id", "extraction_run_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    document_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("tender_documents.id", ondelete="CASCADE"), nullable=False
    )
    extraction_run_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("extraction_runs.id", ondelete="CASCADE"), nullable=False
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    width: Mapped[float] = mapped_column(Float, nullable=False)
    height: Mapped[float] = mapped_column(Float, nullable=False)
    character_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    word_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    is_empty: Mapped[bool] = mapped_column(Boolean, nullable=False)
    text_density: Mapped[float] = mapped_column(Float, nullable=False)
    duration_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    extraction_run: Mapped[ExtractionRunModel] = relationship(back_populates="pages")


class DocumentQualityModel(Base):
    __tablename__ = "document_qualities"
    __table_args__ = (
        CheckConstraint(
            "quality_level IN ('high', 'medium', 'low')",
            name="valid_document_quality_level",
        ),
        CheckConstraint(
            "decision IN ('ready_for_ai', 'needs_ocr', 'manual_review')",
            name="valid_document_quality_decision",
        ),
        UniqueConstraint("extraction_run_id", name="uq_document_qualities_extraction_run"),
        Index("ix_document_qualities_document_id", "document_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    document_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("tender_documents.id", ondelete="CASCADE"), nullable=False
    )
    extraction_run_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("extraction_runs.id", ondelete="CASCADE"), nullable=False
    )
    pages_processed: Mapped[int] = mapped_column(Integer, nullable=False)
    empty_pages: Mapped[int] = mapped_column(Integer, nullable=False)
    characters_extracted: Mapped[int] = mapped_column(BigInteger, nullable=False)
    empty_page_percentage: Mapped[float] = mapped_column(Float, nullable=False)
    text_density: Mapped[float] = mapped_column(Float, nullable=False)
    quality_level: Mapped[str] = mapped_column(String(20), nullable=False)
    decision: Mapped[str] = mapped_column(String(30), nullable=False)
    requires_manual_review: Mapped[bool] = mapped_column(Boolean, nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    extraction_run: Mapped[ExtractionRunModel] = relationship(back_populates="quality")
