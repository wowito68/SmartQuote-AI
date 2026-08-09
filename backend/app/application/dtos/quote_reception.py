from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.application.dtos.document import UploadDocumentFile
from app.domain.quotes.value_objects import ComplianceStatus, MatchStatus, QuoteDocumentStatus, QuoteStatus


@dataclass(frozen=True, slots=True)
class ReceiveQuoteCommand:
    tender_id: UUID
    tender_supplier_id: UUID
    uploaded_by_user_id: UUID
    file: UploadDocumentFile
    rfq_request_id: UUID | None = None
    correlation_id: str | None = None


@dataclass(frozen=True, slots=True)
class AddQuoteDocumentCommand:
    quote_id: UUID
    uploaded_by_user_id: UUID
    file: UploadDocumentFile


@dataclass(frozen=True, slots=True)
class UpdateQuoteItemCommand:
    changed_by_user_id: UUID
    catalog_product_id: UUID | None = None
    brand: str | None = None
    model: str | None = None
    unit: str | None = None
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    total_price: Decimal | None = None
    currency: str | None = None
    delivery_days: int | None = None
    compliance_status: ComplianceStatus | None = None
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class QuoteDocumentResponse:
    id: UUID
    quote_id: UUID
    original_file_name: str
    mime_type: str
    document_type: str
    processing_status: QuoteDocumentStatus
    file_hash: str
    file_size: int
    extractor_name: str | None
    extractor_version: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class EvidenceResponse:
    id: UUID
    quote_item_id: UUID | None
    quote_document_id: UUID
    extraction_run_id: UUID
    field_name: str
    location_type: str
    location_label: str
    fragment: str
    method: str
    confidence: float
    created_at: datetime


@dataclass(frozen=True, slots=True)
class QuoteItemReviewResponse:
    id: UUID
    catalog_product_id: UUID | None
    product_name: str
    description: str | None
    brand: str | None
    model: str | None
    unit: str | None
    quantity: Decimal | None
    unit_price: Decimal | None
    total_price: Decimal | None
    currency: str | None
    delivery_days: int | None
    compliance_status: ComplianceStatus
    match_status: MatchStatus
    match_score: float
    match_reason: str | None
    quoted_specifications: dict[str, str]
    notes: str | None
    confidence: float
    confidence_band: str
    warnings: tuple[str, ...]
    evidence: tuple[EvidenceResponse, ...]
    original_extracted: dict[str, Any]


@dataclass(frozen=True, slots=True)
class QuoteDetailResponse:
    id: UUID
    tender_id: UUID
    tender_supplier_id: UUID
    supplier_id: UUID
    rfq_request_id: UUID | None
    status: QuoteStatus
    currency: str | None
    subtotal_amount: Decimal | None
    tax_amount: Decimal | None
    total_amount: Decimal | None
    delivery_time_days: int | None
    commercial_terms: str | None
    valid_until: datetime | None
    received_at: datetime
    approved_extraction_run_id: UUID | None
    version: int
    manual_edit_count: int
    reviewed_by_user_id: UUID | None
    reviewed_at: datetime | None
    rejection_reason: str | None
    last_error: str | None
    documents: tuple[QuoteDocumentResponse, ...]
    items: tuple[QuoteItemReviewResponse, ...]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ProcessingStatusResponse:
    quote_id: UUID
    quote_status: QuoteStatus
    correlation_id: str | None
    task_status: str | None
    attempt_count: int
    extraction_runs: tuple[dict[str, Any], ...]
    last_error: str | None
