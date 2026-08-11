from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from app.domain.comparison.value_objects import (
    ComparisonStatus,
    MonetaryComparisonStatus,
    NormalizedCompliance,
    OfferStatus,
    QuantityComparisonStatus,
    WarningSeverity,
)


@dataclass(frozen=True, slots=True)
class ComparisonWarningResponse:
    code: str
    severity: WarningSeverity
    message: str
    supplier_id: UUID | None
    quote_id: UUID | None
    quote_item_id: UUID | None


@dataclass(frozen=True, slots=True)
class ComparisonOfferResponse:
    id: UUID
    supplier_id: UUID
    supplier_name: str
    status: OfferStatus
    quote_id: UUID | None
    quote_item_id: UUID | None
    quoted_product_name: str | None
    brand: str | None
    model: str | None
    quantity: Decimal | None
    unit: str | None
    quantity_status: QuantityComparisonStatus
    unit_price: Decimal | None
    total_price: Decimal | None
    currency: str | None
    compliance: NormalizedCompliance
    delivery_days: int | None
    delivery_original_text: str | None
    delivery_normalized: bool
    observations: str | None
    commercial_terms: str | None
    evidence_id: UUID | None
    confidence: float | None
    warnings: tuple[ComparisonWarningResponse, ...]


@dataclass(frozen=True, slots=True)
class ComparisonItemResponse:
    id: UUID
    product_id: UUID
    requested_product: str
    requested_quantity: Decimal | None
    requested_unit: str | None
    monetary_status: MonetaryComparisonStatus
    offers: tuple[ComparisonOfferResponse, ...]
    warnings: tuple[ComparisonWarningResponse, ...]


@dataclass(frozen=True, slots=True)
class ComparisonResponse:
    id: UUID
    tender_id: UUID
    catalog_snapshot_id: UUID
    catalog_version: int
    quotes_version: str
    comparison_version: str
    comparison_key: str
    status: ComparisonStatus
    created_by_user_id: UUID
    source_quote_ids: tuple[UUID, ...]
    items: tuple[ComparisonItemResponse, ...]
    warnings: tuple[ComparisonWarningResponse, ...]
    created_at: datetime
    completed_at: datetime | None
