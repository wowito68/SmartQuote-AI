from datetime import datetime
from decimal import Decimal
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
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.infrastructure.db.base import Base


class QuoteModel(Base):
    __tablename__ = "quotes"
    __table_args__ = (
        CheckConstraint(
            "status IN ('received', 'validating', 'ready_for_analysis', 'analyzing', "
            "'analyzed', 'extracting', 'extracted', 'normalized', 'pending_review', "
            "'approved', 'rejected', 'failed', 'included_in_comparison')",
            name="valid_quote_status",
        ),
        UniqueConstraint(
            "tender_id",
            "supplier_id",
            "file_hash",
            name="uq_quotes_tender_supplier_file_hash",
        ),
        Index("ix_quotes_tender_id", "tender_id"),
        Index("ix_quotes_supplier_id", "supplier_id"),
        Index("ix_quotes_rfq_request_id", "rfq_request_id"),
        Index("ix_quotes_status", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tender_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("tenders.id", ondelete="CASCADE"),
        nullable=False,
    )
    tender_supplier_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("tender_suppliers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    supplier_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("suppliers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    rfq_request_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("rfq_requests.id", ondelete="SET NULL"),
        nullable=True,
    )
    original_file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    uploaded_by_user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    subtotal_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(24, 6), nullable=True
    )
    tax_amount: Mapped[Decimal | None] = mapped_column(Numeric(24, 6), nullable=True)
    total_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(24, 6), nullable=True
    )
    delivery_time_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    commercial_terms: Mapped[str | None] = mapped_column(Text, nullable=True)
    valid_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    approved_extraction_run_id: Mapped[UUID | None] = mapped_column(
        Uuid, nullable=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    manual_edit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reviewed_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class QuoteDocumentModel(Base):
    __tablename__ = "quote_documents"
    __table_args__ = (
        UniqueConstraint(
            "quote_id",
            "file_hash",
            name="uq_quote_documents_quote_hash",
        ),
        Index("ix_quote_documents_quote_id", "quote_id"),
        Index("ix_quote_documents_hash", "file_hash"),
        Index("ix_quote_documents_status", "processing_status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    quote_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("quotes.id", ondelete="CASCADE"),
        nullable=False,
    )
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    original_file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    document_type: Mapped[str] = mapped_column(String(20), nullable=False)
    processing_status: Mapped[str] = mapped_column(String(30), nullable=False)
    extractor_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    extractor_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class QuoteExtractionRunModel(Base):
    __tablename__ = "quote_extraction_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed', 'cancelled', "
            "'reused')",
            name="valid_quote_extraction_run_status",
        ),
        UniqueConstraint(
            "quote_id",
            "idempotency_key",
            name="uq_quote_runs_quote_idempotency",
        ),
        Index("ix_quote_runs_tender_id", "tender_id"),
        Index("ix_quote_runs_quote_id", "quote_id"),
        Index("ix_quote_runs_document_id", "quote_document_id"),
        Index("ix_quote_runs_fingerprint", "extraction_fingerprint"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    quote_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("quotes.id", ondelete="CASCADE"),
        nullable=False,
    )
    quote_document_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("quote_documents.id", ondelete="CASCADE"),
        nullable=True,
    )
    tender_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("tenders.id", ondelete="CASCADE"),
        nullable=False,
    )
    supplier_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("suppliers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    extraction_fingerprint: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    run_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    provider: Mapped[str] = mapped_column(String(100), nullable=False, default="openai")
    extractor_name: Mapped[str] = mapped_column(
        String(100), nullable=False, default="unknown"
    )
    extractor_version: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(50), nullable=False)
    schema_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    provider_response_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    estimated_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(18, 6),
        nullable=False,
        default=Decimal("0"),
    )
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_response: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    reused_from_run_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("quote_extraction_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_approved_source: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class QuoteEvidenceReferenceModel(Base):
    __tablename__ = "quote_evidence_references"
    __table_args__ = (
        Index("ix_quote_evidence_quote_id", "quote_id"),
        Index("ix_quote_evidence_document_id", "quote_document_id"),
        Index("ix_quote_evidence_run_id", "extraction_run_id"),
        Index("ix_quote_evidence_entity", "entity_type", "entity_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    quote_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("quotes.id", ondelete="CASCADE"),
        nullable=False,
    )
    quote_document_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("quote_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    extraction_run_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("quote_extraction_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    entity_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    field_name: Mapped[str] = mapped_column(String(100), nullable=False)
    locator_type: Mapped[str] = mapped_column(String(30), nullable=False)
    locator: Mapped[str] = mapped_column(String(255), nullable=False)
    fragment: Mapped[str] = mapped_column(Text, nullable=False)
    extraction_method: Mapped[str] = mapped_column(String(100), nullable=False)
    finding_status: Mapped[str] = mapped_column(String(30), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class QuoteItemModel(Base):
    __tablename__ = "quote_items"
    __table_args__ = (
        Index("ix_quote_items_quote_id", "quote_id"),
        Index("ix_quote_items_catalog_product_id", "catalog_product_id"),
        Index("ix_quote_items_run_id", "extraction_run_id"),
        Index("ix_quote_items_current", "quote_id", "is_current"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    quote_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("quotes.id", ondelete="CASCADE"),
        nullable=False,
    )
    extraction_run_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("quote_extraction_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    catalog_product_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("catalog_products.id", ondelete="SET NULL"),
        nullable=True,
    )
    product_name: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    brand: Mapped[str | None] = mapped_column(String(255), nullable=True)
    model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(24, 6), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(100), nullable=True)
    unit_price: Mapped[Decimal | None] = mapped_column(
        Numeric(24, 6), nullable=True
    )
    total_price: Mapped[Decimal | None] = mapped_column(
        Numeric(24, 6), nullable=True
    )
    currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    delivery_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    technical_compliance: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    compliance_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="unknown"
    )
    quoted_specifications: Mapped[dict[str, str]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    match_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="unmatched"
    )
    match_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    match_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    warnings: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_evidence_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("quote_evidence_references.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evidence_fragment: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    original_extracted: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class QuoteItemRevisionModel(Base):
    __tablename__ = "quote_item_revisions"
    __table_args__ = (
        Index("ix_quote_item_revisions_quote", "quote_id"),
        Index("ix_quote_item_revisions_item", "quote_item_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    quote_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("quotes.id", ondelete="CASCADE"),
        nullable=False,
    )
    quote_item_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("quote_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    changed_by_user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    before: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    after: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    changed_fields: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class QuoteTaskRecordModel(Base):
    __tablename__ = "quote_task_records"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'retry_pending')",
            name="valid_quote_task_status",
        ),
        UniqueConstraint(
            "correlation_id",
            name="uq_quote_task_records_correlation",
        ),
        Index("ix_quote_task_records_quote", "quote_id"),
        Index("ix_quote_task_records_status", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    quote_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("quotes.id", ondelete="CASCADE"),
        nullable=False,
    )
    correlation_id: Mapped[str] = mapped_column(String(255), nullable=False)
    task_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    force_reprocess: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ComparisonRunModel(Base):
    __tablename__ = "comparison_runs"
    __table_args__ = (
        UniqueConstraint(
            "tender_id",
            "comparison_key",
            name="uq_comparison_tender_key",
        ),
        Index("ix_comparison_runs_tender_id", "tender_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tender_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("tenders.id", ondelete="CASCADE"),
        nullable=False,
    )
    catalog_snapshot_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("catalog_snapshots.id", ondelete="RESTRICT"),
        nullable=False,
    )
    comparison_key: Mapped[str] = mapped_column(String(64), nullable=False)
    approved_quotes_version: Mapped[str] = mapped_column(String(64), nullable=False)
    scoring_config_version: Mapped[str] = mapped_column(String(50), nullable=False)
    rows: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    recommendation: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    generated_by_user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
