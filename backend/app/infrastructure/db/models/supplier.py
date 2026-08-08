from datetime import datetime
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
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.infrastructure.db.base import Base


class SupplierDiscoveryRunModel(Base):
    __tablename__ = "supplier_discovery_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed', 'reused')",
            name="valid_supplier_discovery_run_status",
        ),
        UniqueConstraint(
            "tender_id", "idempotency_key", name="uq_supplier_runs_tender_idempotency"
        ),
        Index("ix_supplier_runs_tender_id", "tender_id"),
        Index("ix_supplier_runs_status", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tender_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("tenders.id", ondelete="CASCADE"), nullable=False
    )
    catalog_snapshot_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("catalog_snapshots.id", ondelete="RESTRICT"), nullable=False
    )
    requested_by_user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    search_provider: Mapped[str] = mapped_column(String(255), nullable=False)
    search_provider_version: Mapped[str] = mapped_column(String(100), nullable=False)
    search_configuration: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    matching_algorithm_version: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    current_stage: Mapped[str] = mapped_column(String(100), nullable=False)
    raw_candidates: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    processed_candidates: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    suppliers_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicates_detected: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    contacts_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    provider_errors: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    search_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    matching_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    reused_from_run_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("supplier_discovery_runs.id", ondelete="SET NULL"), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SupplierModel(Base):
    __tablename__ = "suppliers"
    __table_args__ = (
        Index("ix_suppliers_normalized_domain", "normalized_domain"),
        Index("ix_suppliers_legal_name", "legal_name"),
        Index("ix_suppliers_trade_name", "trade_name"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    legal_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    trade_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    website: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    normalized_domain: Mapped[str | None] = mapped_column(String(500), nullable=True)
    category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    city: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    merged_into_supplier_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class SupplierContactModel(Base):
    __tablename__ = "supplier_contacts"
    __table_args__ = (
        CheckConstraint(
            "contact_type IN ('email', 'phone', 'whatsapp', 'contact_form')",
            name="valid_supplier_contact_type",
        ),
        UniqueConstraint(
            "supplier_id", "identity_key", name="uq_supplier_contacts_identity"
        ),
        Index("ix_supplier_contacts_supplier_id", "supplier_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    supplier_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False
    )
    contact_type: Mapped[str] = mapped_column(String(30), nullable=False)
    value: Mapped[str] = mapped_column(String(2000), nullable=False)
    identity_key: Mapped[str] = mapped_column(String(2100), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    source_url: Mapped[str] = mapped_column(String(2000), nullable=False)
    contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SupplierSourceModel(Base):
    __tablename__ = "supplier_sources"
    __table_args__ = (
        Index("ix_supplier_sources_supplier_id", "supplier_id"),
        Index("ix_supplier_sources_discovery_run_id", "discovery_run_id"),
        Index("ix_supplier_sources_product_id", "product_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    supplier_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False
    )
    provider_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(100), nullable=False)
    source_url: Mapped[str] = mapped_column(String(2000), nullable=False)
    source_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    discovery_run_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("supplier_discovery_runs.id", ondelete="SET NULL"), nullable=True
    )
    product_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("catalog_products.id", ondelete="SET NULL"), nullable=True
    )
    query: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    source_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, nullable=False, default=dict)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TenderSupplierModel(Base):
    __tablename__ = "tender_suppliers"
    __table_args__ = (
        CheckConstraint(
            "status IN ('candidate', 'contacts_found', 'pending_review', 'approved', "
            "'rejected', 'merged', 'contacted', 'responded', 'inactive')",
            name="valid_tender_supplier_status",
        ),
        UniqueConstraint("tender_id", "supplier_id", name="uq_tender_suppliers_master"),
        Index("ix_tender_suppliers_tender_id", "tender_id"),
        Index("ix_tender_suppliers_supplier_id", "supplier_id"),
        Index("ix_tender_suppliers_status", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tender_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("tenders.id", ondelete="CASCADE"), nullable=False
    )
    supplier_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False
    )
    discovery_run_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("supplier_discovery_runs.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    is_manual: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reviewed_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    merged_into_tender_supplier_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("tender_suppliers.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ProductSupplierMatchModel(Base):
    __tablename__ = "product_supplier_matches"
    __table_args__ = (
        CheckConstraint(
            "match_status IN ('candidate', 'confirmed', 'rejected')",
            name="valid_product_supplier_match_status",
        ),
        UniqueConstraint(
            "tender_supplier_id", "product_id", name="uq_product_supplier_match"
        ),
        Index("ix_product_supplier_matches_tender_supplier", "tender_supplier_id"),
        Index("ix_product_supplier_matches_product", "product_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tender_supplier_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("tender_suppliers.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("catalog_products.id", ondelete="CASCADE"), nullable=False
    )
    score: Mapped[float] = mapped_column(Float, nullable=False)
    components: Mapped[dict[str, float]] = mapped_column(JSON, nullable=False)
    reasons: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    algorithm_version: Mapped[str] = mapped_column(String(100), nullable=False)
    match_status: Mapped[str] = mapped_column(String(20), nullable=False, default="candidate")
    source_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SupplierMergeSuggestionModel(Base):
    __tablename__ = "supplier_merge_suggestions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'accepted', 'rejected')",
            name="valid_supplier_merge_suggestion_status",
        ),
        UniqueConstraint(
            "source_supplier_id",
            "target_supplier_id",
            "discovery_run_id",
            name="uq_supplier_merge_suggestion_pair_run",
        ),
        Index("ix_supplier_merge_source", "source_supplier_id"),
        Index("ix_supplier_merge_target", "target_supplier_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    source_supplier_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False
    )
    target_supplier_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False
    )
    discovery_run_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("supplier_discovery_runs.id", ondelete="SET NULL"), nullable=True
    )
    score: Mapped[float] = mapped_column(Float, nullable=False)
    signals: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    reviewed_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
