from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
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


class ComparisonModel(Base):
    __tablename__ = "comparisons"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'building', 'ready', 'invalid', 'archived')",
            name="valid_comparison_status",
        ),
        UniqueConstraint(
            "tender_id",
            "comparison_key",
            name="uq_comparisons_tender_key",
        ),
        Index("ix_comparisons_tender_id", "tender_id"),
        Index("ix_comparisons_status", "status"),
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
    catalog_version: Mapped[int] = mapped_column(Integer, nullable=False)
    quotes_version: Mapped[str] = mapped_column(String(64), nullable=False)
    comparison_version: Mapped[str] = mapped_column(String(50), nullable=False)
    comparison_key: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_quote_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    warnings: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ComparisonItemModel(Base):
    __tablename__ = "comparison_items"
    __table_args__ = (
        CheckConstraint(
            "monetary_status IN ('comparable', 'requires_normalization', 'insufficient_data')",
            name="valid_comparison_monetary_status",
        ),
        UniqueConstraint(
            "comparison_id",
            "product_id",
            name="uq_comparison_items_product",
        ),
        Index("ix_comparison_items_comparison_id", "comparison_id"),
        Index("ix_comparison_items_product_id", "product_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    comparison_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("comparisons.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("catalog_products.id", ondelete="RESTRICT"),
        nullable=False,
    )
    requested_product_name: Mapped[str] = mapped_column(String(500), nullable=False)
    requested_quantity: Mapped[Decimal | None] = mapped_column(Numeric(24, 6), nullable=True)
    requested_unit: Mapped[str | None] = mapped_column(String(100), nullable=True)
    monetary_status: Mapped[str] = mapped_column(String(30), nullable=False)
    warnings: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class ComparisonOfferModel(Base):
    __tablename__ = "comparison_offers"
    __table_args__ = (
        CheckConstraint(
            "status IN ('quoted', 'missing', 'invalid')",
            name="valid_comparison_offer_status",
        ),
        CheckConstraint(
            "quantity_status IN ('matched', 'quantity_mismatch', 'unit_mismatch', 'unknown')",
            name="valid_comparison_quantity_status",
        ),
        CheckConstraint(
            "compliance_status IN ('compliant', 'partially_compliant', 'non_compliant', 'unknown')",
            name="valid_comparison_compliance_status",
        ),
        UniqueConstraint(
            "comparison_item_id",
            "supplier_id",
            name="uq_comparison_offers_supplier",
        ),
        Index("ix_comparison_offers_item_id", "comparison_item_id"),
        Index("ix_comparison_offers_supplier_id", "supplier_id"),
        Index("ix_comparison_offers_quote_id", "quote_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    comparison_item_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("comparison_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    supplier_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("suppliers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    supplier_name: Mapped[str] = mapped_column(String(500), nullable=False)
    quote_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("quotes.id", ondelete="SET NULL"),
        nullable=True,
    )
    quote_item_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("quote_items.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    quoted_product_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    brand: Mapped[str | None] = mapped_column(String(255), nullable=True)
    model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    quoted_quantity: Mapped[Decimal | None] = mapped_column(Numeric(24, 6), nullable=True)
    quoted_unit: Mapped[str | None] = mapped_column(String(100), nullable=True)
    quantity_status: Mapped[str] = mapped_column(String(30), nullable=False)
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(24, 6), nullable=True)
    total_price: Mapped[Decimal | None] = mapped_column(Numeric(24, 6), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    compliance_status: Mapped[str] = mapped_column(String(30), nullable=False)
    delivery_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    delivery_original_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivery_normalized: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    observations: Mapped[str | None] = mapped_column(Text, nullable=True)
    commercial_terms: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("quote_evidence_references.id", ondelete="SET NULL"),
        nullable=True,
    )
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    warnings: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
