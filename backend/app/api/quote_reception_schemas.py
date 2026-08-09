from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.quotes.value_objects import ComplianceStatus, MatchStatus, QuoteDocumentStatus, QuoteStatus


class QuoteDocumentResponseSchema(BaseModel):
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
    model_config = ConfigDict(from_attributes=True)


class EvidenceResponseSchema(BaseModel):
    id: UUID
    quote_item_id: UUID | None
    quote_document_id: UUID
    extraction_run_id: UUID
    field_name: str
    location_type: str
    location_label: str
    fragment: str
    method: str
    confidence: float = Field(ge=0, le=1)
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class QuoteItemReviewResponseSchema(BaseModel):
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
    match_score: float = Field(ge=0, le=1)
    match_reason: str | None
    quoted_specifications: dict[str, str]
    notes: str | None
    confidence: float = Field(ge=0, le=1)
    confidence_band: str
    warnings: tuple[str, ...]
    evidence: tuple[EvidenceResponseSchema, ...]
    original_extracted: dict[str, Any]
    model_config = ConfigDict(from_attributes=True)


class QuoteDetailResponseSchema(BaseModel):
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
    documents: tuple[QuoteDocumentResponseSchema, ...]
    items: tuple[QuoteItemReviewResponseSchema, ...]
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class QuoteUploadResponseSchema(BaseModel):
    quote: QuoteDetailResponseSchema
    duplicate: bool


class QuoteProcessingRequestSchema(BaseModel):
    requested_by_user_id: UUID


class QuoteItemUpdateSchema(BaseModel):
    changed_by_user_id: UUID
    catalog_product_id: UUID | None = None
    brand: str | None = Field(default=None, max_length=255)
    model: str | None = Field(default=None, max_length=255)
    unit: str | None = Field(default=None, max_length=50)
    quantity: Decimal | None = Field(default=None, gt=0)
    unit_price: Decimal | None = Field(default=None, ge=0)
    total_price: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    delivery_days: int | None = Field(default=None, ge=0)
    compliance_status: ComplianceStatus | None = None
    notes: str | None = Field(default=None, max_length=4000)


class QuoteReviewActionSchema(BaseModel):
    reviewer_user_id: UUID
    reason: str | None = Field(default=None, max_length=2000)


class ProcessingStatusResponseSchema(BaseModel):
    quote_id: UUID
    quote_status: QuoteStatus
    correlation_id: str | None
    task_status: str | None
    attempt_count: int
    extraction_runs: tuple[dict[str, Any], ...]
    last_error: str | None
    model_config = ConfigDict(from_attributes=True)


class QuoteDocumentsResponseSchema(BaseModel):
    items: tuple[QuoteDocumentResponseSchema, ...]
    total: int


class QuoteItemsResponseSchema(BaseModel):
    items: tuple[QuoteItemReviewResponseSchema, ...]
    total: int
