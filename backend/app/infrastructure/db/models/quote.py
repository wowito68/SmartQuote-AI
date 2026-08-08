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
            "status IN ('received', 'validating', 'extracting', 'extracted', 'normalized', "
            "'pending_review', 'approved', 'rejected', 'included_in_comparison')",
            name="valid_quote_status",
        ),
        UniqueConstraint(
            "tender_id", "supplier_id", "file_hash", name="uq_quotes_tender_supplier_file_hash"
        ),
        Index("ix_quotes_tender_id", "tender_id"),
        Index("ix_quotes_supplier_id", "supplier_id"),
        Index("ix_quotes_status", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tender_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("tenders.id", ondelete="CASCADE"), nullable=False
    )
    tender_supplier_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("tender_suppliers.id", ondelete="RESTRICT"), nullable=False
    )
    supplier_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False
    )
    original_file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    uploaded_by_user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    manual_edit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reviewed_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class QuoteExtractionRunModel(Base):
    __tablename__ = "quote_extraction_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed', 'reused')",
            name="valid_quote_extraction_run_status",
        ),
        UniqueConstraint("quote_id", "idempotency_key", name="uq_quote_runs_quote_idempotency"),
        Index("ix_quote_runs_tender_id", "tender_id"),
        Index("ix_quote_runs_quote_id", "quote_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    quote_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("quotes.id", ondelete="CASCADE"), nullable=False
    )
    tender_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("tenders.id", ondelete="CASCADE"), nullable=False
    )
    supplier_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
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
        Numeric(18, 6), nullable=False, default=Decimal("0")
    )
    raw_response: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class QuoteItemModel(Base):
    __tablename__ = "quote_items"
    __table_args__ = (
        Index("ix_quote_items_quote_id", "quote_id"),
        Index("ix_quote_items_catalog_product_id", "catalog_product_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    quote_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("quotes.id", ondelete="CASCADE"), nullable=False
    )
    catalog_product_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("catalog_products.id", ondelete="SET NULL"), nullable=True
    )
    product_name: Mapped[str] = mapped_column(String(500), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(255), nullable=True)
    model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(24, 6), nullable=True)
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(24, 6), nullable=True)
    total_price: Mapped[Decimal | None] = mapped_column(Numeric(24, 6), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    delivery_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    technical_compliance: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evidence_fragment: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ComparisonRunModel(Base):
    __tablename__ = "comparison_runs"
    __table_args__ = (
        UniqueConstraint("tender_id", "comparison_key", name="uq_comparison_tender_key"),
        Index("ix_comparison_runs_tender_id", "tender_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tender_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("tenders.id", ondelete="CASCADE"), nullable=False
    )
    catalog_snapshot_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("catalog_snapshots.id", ondelete="RESTRICT"), nullable=False
    )
    comparison_key: Mapped[str] = mapped_column(String(64), nullable=False)
    approved_quotes_version: Mapped[str] = mapped_column(String(64), nullable=False)
    scoring_config_version: Mapped[str] = mapped_column(String(50), nullable=False)
    rows: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    recommendation: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    generated_by_user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
