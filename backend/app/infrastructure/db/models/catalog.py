from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.infrastructure.db.base import Base


class AIExtractionRunModel(Base):
    __tablename__ = "ai_extraction_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed', 'reused')",
            name="valid_ai_extraction_run_status",
        ),
        UniqueConstraint(
            "document_id", "idempotency_key", name="uq_ai_runs_document_idempotency"
        ),
        Index("ix_ai_runs_tender_id", "tender_id"),
        Index("ix_ai_runs_document_id", "document_id"),
        Index("ix_ai_runs_status", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tender_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("tenders.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("tender_documents.id", ondelete="CASCADE"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    temperature: Mapped[float] = mapped_column(Float, nullable=False)
    schema_version: Mapped[str] = mapped_column(String(50), nullable=False)
    schema_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    provider_response_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    estimated_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, default=Decimal("0")
    )
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    products_detected: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    invalid_json_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    raw_response: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    validation_errors: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    error_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    reused_from_run_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("ai_extraction_runs.id", ondelete="SET NULL"), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CatalogProductModel(Base):
    __tablename__ = "catalog_products"
    __table_args__ = (
        CheckConstraint(
            "status IN ('candidate', 'normalized', 'pending_review', 'approved', 'rejected')",
            name="valid_catalog_product_status",
        ),
        Index("ix_catalog_products_tender_id", "tender_id"),
        Index("ix_catalog_products_ai_run_id", "ai_extraction_run_id"),
        Index("ix_catalog_products_status", "status"),
        Index("ix_catalog_products_source_document_id", "source_document_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tender_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("tenders.id", ondelete="CASCADE"), nullable=False
    )
    ai_extraction_run_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("ai_extraction_runs.id", ondelete="CASCADE"), nullable=False
    )
    source_document_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("tender_documents.id", ondelete="RESTRICT"), nullable=False
    )
    original_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    item_number: Mapped[str | None] = mapped_column(String(255), nullable=True)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(24, 6), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(100), nullable=True)
    category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    specifications: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)
    observations: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    duplicate_of_product_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("catalog_products.id", ondelete="SET NULL"), nullable=True
    )
    manual_edit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reviewed_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class CatalogProductRevisionModel(Base):
    __tablename__ = "catalog_product_revisions"
    __table_args__ = (Index("ix_catalog_revisions_product_id", "product_id"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    product_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("catalog_products.id", ondelete="CASCADE"), nullable=False
    )
    changed_by_user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    before_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    after_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    changed_fields: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ExtractedEvidenceModel(Base):
    __tablename__ = "extracted_evidence"
    __table_args__ = (
        Index("ix_extracted_evidence_product_id", "product_id"),
        Index("ix_extracted_evidence_document_id", "document_id"),
        Index("ix_extracted_evidence_ai_run_id", "ai_extraction_run_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    product_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("catalog_products.id", ondelete="CASCADE"), nullable=False
    )
    ai_extraction_run_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("ai_extraction_runs.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("tender_documents.id", ondelete="RESTRICT"), nullable=False
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    text_fragment: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class EvidenceReferenceModel(Base):
    __tablename__ = "evidence_references"
    __table_args__ = (Index("ix_evidence_references_evidence_id", "evidence_id"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    evidence_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("extracted_evidence.id", ondelete="CASCADE"), nullable=False
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    x0: Mapped[float | None] = mapped_column(Float, nullable=True)
    y0: Mapped[float | None] = mapped_column(Float, nullable=True)
    x1: Mapped[float | None] = mapped_column(Float, nullable=True)
    y1: Mapped[float | None] = mapped_column(Float, nullable=True)


class CatalogSnapshotModel(Base):
    __tablename__ = "catalog_snapshots"
    __table_args__ = (
        UniqueConstraint("tender_id", "version", name="uq_catalog_snapshots_tender_version"),
        Index("ix_catalog_snapshots_tender_id", "tender_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tender_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("tenders.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    approved_by_user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    products: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
