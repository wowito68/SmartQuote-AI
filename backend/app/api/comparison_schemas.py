from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from app.domain.comparison.value_objects import (
    ComparisonStatus,
    MonetaryComparisonStatus,
    NormalizedCompliance,
    OfferStatus,
    QuantityComparisonStatus,
    WarningSeverity,
)


class ComparisonGenerateRequestSchema(BaseModel):
    created_by_user_id: UUID = Field(
        validation_alias=AliasChoices("created_by_user_id", "generated_by_user_id")
    )


class ComparisonWarningSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    severity: WarningSeverity
    message: str
    supplier_id: UUID | None
    quote_id: UUID | None
    quote_item_id: UUID | None


class ComparisonOfferSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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
    confidence: float | None = Field(default=None, ge=0, le=1)
    warnings: tuple[ComparisonWarningSchema, ...]


class ComparisonItemSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    product_id: UUID
    requested_product: str
    requested_quantity: Decimal | None
    requested_unit: str | None
    monetary_status: MonetaryComparisonStatus
    offers: tuple[ComparisonOfferSchema, ...]
    warnings: tuple[ComparisonWarningSchema, ...]


class ComparisonResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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
    items: tuple[ComparisonItemSchema, ...]
    warnings: tuple[ComparisonWarningSchema, ...]
    created_at: datetime
    completed_at: datetime | None
