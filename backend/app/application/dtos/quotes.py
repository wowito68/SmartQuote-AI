from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.application.dtos.document import UploadDocumentFile
from app.domain.quotes.value_objects import QuoteStatus


@dataclass(frozen=True, slots=True)
class UploadQuoteCommand:
    tender_id: UUID
    tender_supplier_id: UUID
    uploaded_by_user_id: UUID
    file: UploadDocumentFile
    correlation_id: str | None = None


@dataclass(frozen=True, slots=True)
class QuoteItemResponse:
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


@dataclass(frozen=True, slots=True)
class QuoteResponse:
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
    items: tuple[QuoteItemResponse, ...]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class QuoteReviewCommand:
    reviewer_user_id: UUID
    action: str
    rejection_reason: str | None = None


@dataclass(frozen=True, slots=True)
class ComparisonResponse:
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
