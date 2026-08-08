from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.quotes.value_objects import QuoteStatus


class QuoteItemResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    catalog_product_id: UUID | None
    product_name: str
    brand: str | None
    model: str | None
    quantity: Decimal | None
    unit_price: Decimal | None
    total_price: Decimal | None
    currency: str | None
    delivery_days: int | None
    technical_compliance: bool | None
    notes: str | None
    source_page: int | None
    evidence_fragment: str | None
    confidence: float


class QuoteResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tender_id: UUID
    tender_supplier_id: UUID
    supplier_id: UUID
    original_file_name: str
    file_hash: str
    file_size: int
    mime_type: str
    status: QuoteStatus
    version: int
    manual_edit_count: int
    reviewed_by_user_id: UUID | None
    reviewed_at: datetime | None
    rejection_reason: str | None
    last_error: str | None
    items: tuple[QuoteItemResponseSchema, ...]
    created_at: datetime
    updated_at: datetime


class TenderQuotesResponseSchema(BaseModel):
    items: tuple[QuoteResponseSchema, ...]
    total: int


class QuoteReviewRequestSchema(BaseModel):
    reviewer_user_id: UUID
    action: Literal["approve", "reject"]
    rejection_reason: str | None = Field(default=None, max_length=2000)


class ComparisonGenerateRequestSchema(BaseModel):
    generated_by_user_id: UUID


class ComparisonResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tender_id: UUID
    catalog_snapshot_id: UUID
    comparison_key: str
    approved_quotes_version: str
    scoring_config_version: str
    rows: tuple[dict[str, Any], ...]
    recommendation: dict[str, Any]
    generated_by_user_id: UUID
    created_at: datetime
