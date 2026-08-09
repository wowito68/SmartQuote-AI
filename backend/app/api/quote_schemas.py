from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.quotes.value_objects import (
    ComplianceStatus,
    ProductMatchStatus,
    QuoteDocumentProcessingStatus,
    QuoteDocumentType,
    QuoteExtractionRunStatus,
    QuoteStatus,
    QuoteTaskStatus,
)


class QuoteDocumentResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    quote_id: UUID
    original_file_name: str
    mime_type: str
    file_size: int
    file_hash: str
    document_type: QuoteDocumentType
    processing_status: QuoteDocumentProcessingStatus
    extractor_name: str | None
    extractor_version: str | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime


class QuoteExtractionRunResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    quote_document_id: UUID | None
    run_number: int
    provider: str
    model: str
    prompt_version: str
    schema_version: str
    extractor_name: str
    extractor_version: str
    status: QuoteExtractionRunStatus
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: Decimal
    duration_ms: int | None
    is_approved_source: bool
    error_type: str | None
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class QuoteItemResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    catalog_product_id: UUID | None
    extraction_run_id: UUID | None
    product_name: str
    description: str | None
    brand: str | None
    model: str | None
    quantity: Decimal | None
    unit: str | None
    unit_price: Decimal | None
    total_price: Decimal | None
    currency: str | None
    delivery_days: int | None
    technical_compliance: bool | None
    compliance_status: ComplianceStatus
    quoted_specifications: dict[str, str]
    match_status: ProductMatchStatus
    match_score: float = Field(ge=0, le=1)
    match_reason: str | None
    warnings: tuple[str, ...]
    notes: str | None
    source_evidence_id: UUID | None
    source_page: int | None
    evidence_fragment: str | None
    confidence: float = Field(ge=0, le=1)
    original_extracted: dict[str, Any]


class QuoteResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tender_id: UUID
    tender_supplier_id: UUID
    supplier_id: UUID
    rfq_request_id: UUID | None
    original_file_name: str
    file_hash: str
    file_size: int
    mime_type: str
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
    items: tuple[QuoteItemResponseSchema, ...]
    documents: tuple[QuoteDocumentResponseSchema, ...]
    extraction_runs: tuple[QuoteExtractionRunResponseSchema, ...]
    created_at: datetime
    updated_at: datetime


class TenderQuotesResponseSchema(BaseModel):
    items: tuple[QuoteResponseSchema, ...]
    total: int


class QuoteUploadResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    quote: QuoteResponseSchema
    duplicate_detected: bool
    queued: bool


class QuoteEvidenceResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    quote_document_id: UUID
    extraction_run_id: UUID
    entity_type: str
    entity_id: UUID
    field_name: str
    locator_type: str
    locator: str
    fragment: str
    extraction_method: str
    finding_status: str
    confidence: float = Field(ge=0, le=1)
    created_at: datetime


class QuoteEvidenceListResponseSchema(BaseModel):
    items: tuple[QuoteEvidenceResponseSchema, ...]
    total: int


class QuoteDocumentsResponseSchema(BaseModel):
    items: tuple[QuoteDocumentResponseSchema, ...]
    total: int


class QuoteItemsResponseSchema(BaseModel):
    items: tuple[QuoteItemResponseSchema, ...]
    total: int


class QuoteProcessingStatusResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    quote_id: UUID
    quote_status: QuoteStatus
    task_id: UUID | None
    task_status: QuoteTaskStatus | None
    correlation_id: str | None
    attempt_count: int
    extraction_run_id: UUID | None
    extraction_status: QuoteExtractionRunStatus | None
    last_error: str | None


class UpdateQuoteItemRequestSchema(BaseModel):
    changed_by_user_id: UUID
    catalog_product_id: UUID | None = None
    product_name: str | None = Field(default=None, max_length=500)
    description: str | None = Field(default=None, max_length=4000)
    brand: str | None = Field(default=None, max_length=255)
    model: str | None = Field(default=None, max_length=255)
    quantity: Decimal | None = Field(default=None, gt=0)
    unit: str | None = Field(default=None, max_length=100)
    unit_price: Decimal | None = Field(default=None, ge=0)
    total_price: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    delivery_days: int | None = Field(default=None, ge=0)
    compliance_status: ComplianceStatus | None = None
    notes: str | None = Field(default=None, max_length=4000)


class QuoteSubmitReviewRequestSchema(BaseModel):
    reviewer_user_id: UUID


class QuoteApprovalRequestSchema(BaseModel):
    reviewer_user_id: UUID


class QuoteRejectionRequestSchema(BaseModel):
    reviewer_user_id: UUID
    reason: str = Field(min_length=1, max_length=2000)


class QuoteProcessRequestSchema(BaseModel):
    requested_by_user_id: UUID


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
