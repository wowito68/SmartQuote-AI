from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from app.application.dtos.document import UploadDocumentFile
from app.domain.quotes.value_objects import (
    ComplianceStatus,
    ProductMatchStatus,
    QuoteDocumentProcessingStatus,
    QuoteDocumentType,
    QuoteExtractionRunStatus,
    QuoteStatus,
    QuoteTaskStatus,
)


@dataclass(frozen=True, slots=True)
class UploadQuoteCommand:
    tender_id: UUID
    tender_supplier_id: UUID
    uploaded_by_user_id: UUID
    file: UploadDocumentFile
    correlation_id: str | None = None
    rfq_request_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class UploadQuoteDocumentCommand:
    tender_id: UUID
    supplier_id: UUID
    uploaded_by_user_id: UUID
    file: UploadDocumentFile
    rfq_request_id: UUID | None = None
    correlation_id: str | None = None
    auto_process: bool = False


@dataclass(frozen=True, slots=True)
class UpdateQuoteItemCommand:
    changed_by_user_id: UUID
    catalog_product_id: UUID | None = None
    product_name: str | None = None
    description: str | None = None
    brand: str | None = None
    model: str | None = None
    quantity: Decimal | None = None
    unit: str | None = None
    unit_price: Decimal | None = None
    total_price: Decimal | None = None
    currency: str | None = None
    delivery_days: int | None = None
    compliance_status: ComplianceStatus | None = None
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class QuoteReviewCommand:
    reviewer_user_id: UUID
    action: Literal["approve", "reject"]
    rejection_reason: str | None = None


@dataclass(frozen=True, slots=True)
class QuoteDocumentResponse:
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


@dataclass(frozen=True, slots=True)
class QuoteEvidenceResponse:
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
    confidence: float
    created_at: datetime


@dataclass(frozen=True, slots=True)
class QuoteExtractionRunResponse:
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


@dataclass(frozen=True, slots=True)
class QuoteItemResponse:
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
    match_score: float
    match_reason: str | None
    warnings: tuple[str, ...]
    notes: str | None
    source_evidence_id: UUID | None
    source_page: int | None
    evidence_fragment: str | None
    confidence: float
    original_extracted: dict[str, Any]


@dataclass(frozen=True, slots=True)
class QuoteResponse:
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
    items: tuple[QuoteItemResponse, ...]
    documents: tuple[QuoteDocumentResponse, ...]
    extraction_runs: tuple[QuoteExtractionRunResponse, ...]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class QuoteProcessingStatusResponse:
    quote_id: UUID
    quote_status: QuoteStatus
    task_id: UUID | None
    task_status: QuoteTaskStatus | None
    correlation_id: str | None
    attempt_count: int
    extraction_run_id: UUID | None
    extraction_status: QuoteExtractionRunStatus | None
    last_error: str | None


@dataclass(frozen=True, slots=True)
class QuoteUploadResponse:
    quote: QuoteResponse
    duplicate_detected: bool
    queued: bool


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
