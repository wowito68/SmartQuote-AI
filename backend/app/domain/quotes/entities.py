from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID, uuid4

from app.domain.quotes.exceptions import InvalidQuoteState
from app.domain.quotes.value_objects import (
    ComplianceStatus,
    EvidenceLocationType,
    MatchStatus,
    QuoteDocumentStatus,
    QuoteExtractionRunStatus,
    QuoteStatus,
    QuoteTaskStatus,
)
from app.domain.shared.exceptions import ValidationError


def _now() -> datetime:
    return datetime.now(UTC)


def _clean(value: str | None, *, limit: int | None = None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.split())
    if not normalized:
        return None
    return normalized[:limit] if limit else normalized


def _decimal(value: Decimal | str | float | int | None, field_name: str) -> Decimal | None:
    if value is None:
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError(f"{field_name} is invalid.") from exc
    if not result.is_finite() or result < 0:
        raise ValidationError(f"{field_name} must be non-negative and finite.")
    return result


_QUOTE_TRANSITIONS: dict[QuoteStatus, frozenset[QuoteStatus]] = {
    QuoteStatus.RECEIVED: frozenset({QuoteStatus.VALIDATING, QuoteStatus.REJECTED, QuoteStatus.FAILED}),
    QuoteStatus.VALIDATING: frozenset({QuoteStatus.EXTRACTING, QuoteStatus.FAILED}),
    QuoteStatus.EXTRACTING: frozenset({QuoteStatus.EXTRACTED, QuoteStatus.FAILED}),
    QuoteStatus.EXTRACTED: frozenset({QuoteStatus.NORMALIZED, QuoteStatus.FAILED}),
    QuoteStatus.NORMALIZED: frozenset({QuoteStatus.PENDING_REVIEW, QuoteStatus.FAILED}),
    QuoteStatus.PENDING_REVIEW: frozenset({QuoteStatus.APPROVED, QuoteStatus.REJECTED, QuoteStatus.EXTRACTING}),
    QuoteStatus.APPROVED: frozenset({QuoteStatus.INCLUDED_IN_COMPARISON}),
    QuoteStatus.REJECTED: frozenset(),
    QuoteStatus.FAILED: frozenset({QuoteStatus.EXTRACTING, QuoteStatus.REJECTED}),
    QuoteStatus.INCLUDED_IN_COMPARISON: frozenset(),
}


@dataclass(slots=True)
class Quote:
    tender_id: UUID
    tender_supplier_id: UUID
    supplier_id: UUID
    original_file_name: str
    storage_key: str
    mime_type: str
    file_size: int
    file_hash: str
    uploaded_by_user_id: UUID
    id: UUID = field(default_factory=uuid4)
    rfq_request_id: UUID | None = None
    currency: str | None = None
    subtotal_amount: Decimal | None = None
    tax_amount: Decimal | None = None
    total_amount: Decimal | None = None
    delivery_time_days: int | None = None
    commercial_terms: str | None = None
    valid_until: datetime | None = None
    received_at: datetime = field(default_factory=_now)
    approved_extraction_run_id: UUID | None = None
    status: QuoteStatus = QuoteStatus.RECEIVED
    version: int = 1
    manual_edit_count: int = 0
    reviewed_by_user_id: UUID | None = None
    reviewed_at: datetime | None = None
    rejection_reason: str | None = None
    last_error: str | None = None
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)

    def __post_init__(self) -> None:
        self.original_file_name = _clean(self.original_file_name, limit=255) or ""
        self.storage_key = _clean(self.storage_key, limit=1024) or ""
        self.mime_type = _clean(self.mime_type, limit=255) or ""
        if not self.original_file_name or not self.storage_key:
            raise ValidationError("Quote file metadata is incomplete.")
        if self.file_size <= 0:
            raise ValidationError("Quote file size must be positive.")
        if len(self.file_hash) != 64:
            raise ValidationError("Quote file hash must be a SHA-256 digest.")
        if self.version < 1:
            raise ValidationError("Quote version must be positive.")
        self.currency = (_clean(self.currency, limit=3) or "").upper() or None
        if self.currency and (len(self.currency) != 3 or not self.currency.isalpha()):
            raise ValidationError("Quote currency must be a three-letter code.")
        self.subtotal_amount = _decimal(self.subtotal_amount, "Subtotal")
        self.tax_amount = _decimal(self.tax_amount, "Tax amount")
        self.total_amount = _decimal(self.total_amount, "Total amount")
        if self.delivery_time_days is not None and self.delivery_time_days < 0:
            raise ValidationError("Quote delivery time cannot be negative.")
        self.commercial_terms = _clean(self.commercial_terms, limit=10000)

    def _transition(self, target: QuoteStatus) -> None:
        if target is self.status:
            return
        if target not in _QUOTE_TRANSITIONS[self.status]:
            raise InvalidQuoteState(f"Quote cannot transition from {self.status.value} to {target.value}.")
        self.status = target
        self.updated_at = _now()

    def start_validation(self) -> None:
        self._transition(QuoteStatus.VALIDATING)
        self.last_error = None

    def start_extraction(self) -> None:
        self._transition(QuoteStatus.EXTRACTING)
        self.last_error = None

    def mark_extracted(self) -> None:
        self._transition(QuoteStatus.EXTRACTED)

    def mark_normalized(self) -> None:
        self._transition(QuoteStatus.NORMALIZED)

    def start_review(self) -> None:
        self._transition(QuoteStatus.PENDING_REVIEW)

    def approve(self, reviewer_user_id: UUID, extraction_run_id: UUID | None = None) -> None:
        self._transition(QuoteStatus.APPROVED)
        self.reviewed_by_user_id = reviewer_user_id
        self.reviewed_at = self.updated_at
        self.rejection_reason = None
        self.approved_extraction_run_id = extraction_run_id or self.approved_extraction_run_id

    def reject(self, reviewer_user_id: UUID, reason: str) -> None:
        cleaned = _clean(reason, limit=2000)
        if not cleaned:
            raise ValidationError("A quote rejection reason is required.")
        self._transition(QuoteStatus.REJECTED)
        self.reviewed_by_user_id = reviewer_user_id
        self.reviewed_at = self.updated_at
        self.rejection_reason = cleaned

    def include_in_comparison(self) -> None:
        self._transition(QuoteStatus.INCLUDED_IN_COMPARISON)

    def record_manual_edit(self) -> None:
        if self.status is not QuoteStatus.PENDING_REVIEW:
            raise InvalidQuoteState("Only pending-review quotes can be edited.")
        self.manual_edit_count += 1
        self.version += 1
        self.updated_at = _now()

    def record_error(self, error: Exception, *, terminal: bool = False) -> None:
        self.last_error = f"{type(error).__name__}: {error}"[:4000]
        if terminal and self.status not in {QuoteStatus.APPROVED, QuoteStatus.REJECTED, QuoteStatus.INCLUDED_IN_COMPARISON}:
            if QuoteStatus.FAILED in _QUOTE_TRANSITIONS[self.status]:
                self._transition(QuoteStatus.FAILED)
        self.updated_at = _now()


@dataclass(slots=True)
class QuoteDocument:
    quote_id: UUID
    storage_key: str
    original_file_name: str
    mime_type: str
    document_type: str
    file_hash: str
    file_size: int
    id: UUID = field(default_factory=uuid4)
    processing_status: QuoteDocumentStatus = QuoteDocumentStatus.STORED
    extractor_name: str | None = None
    extractor_version: str | None = None
    created_at: datetime = field(default_factory=_now)

    def __post_init__(self) -> None:
        if len(self.file_hash) != 64 or self.file_size <= 0:
            raise ValidationError("Quote document file metadata is invalid.")
        if not _clean(self.storage_key) or not _clean(self.original_file_name):
            raise ValidationError("Quote document storage metadata is required.")


@dataclass(slots=True)
class QuoteExtractionRun:
    quote_id: UUID
    tender_id: UUID
    supplier_id: UUID
    idempotency_key: str
    extractor_version: str
    prompt_version: str
    model: str
    schema_version: str
    schema_hash: str
    id: UUID = field(default_factory=uuid4)
    status: QuoteExtractionRunStatus = QuoteExtractionRunStatus.QUEUED
    provider: str = "openai"
    entity_type: str = "quote"
    provider_response_id: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: Decimal = Decimal("0")
    duration_ms: int | None = None
    raw_response: dict[str, Any] | None = None
    error_type: str | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime = field(default_factory=_now)

    def __post_init__(self) -> None:
        if len(self.idempotency_key) != 64 or len(self.schema_hash) != 64:
            raise ValidationError("Quote extraction keys must be SHA-256 digests.")
        for value in (self.extractor_version, self.prompt_version, self.model, self.schema_version):
            if not value.strip():
                raise ValidationError("Quote extraction version metadata is required.")

    def start(self) -> None:
        if self.status in {QuoteExtractionRunStatus.COMPLETED, QuoteExtractionRunStatus.REUSED}:
            return
        self.status = QuoteExtractionRunStatus.RUNNING
        self.started_at = self.started_at or _now()
        self.completed_at = None
        self.error_type = None
        self.error_message = None

    def complete(self, *, provider_response_id: str | None, input_tokens: int, output_tokens: int,
                 estimated_cost_usd: Decimal, raw_response: dict[str, Any], duration_ms: int | None = None) -> None:
        self.status = QuoteExtractionRunStatus.COMPLETED
        self.provider_response_id = provider_response_id
        self.input_tokens = max(input_tokens, 0)
        self.output_tokens = max(output_tokens, 0)
        self.estimated_cost_usd = max(estimated_cost_usd, Decimal("0"))
        self.raw_response = raw_response
        self.duration_ms = max(duration_ms or 0, 0)
        self.completed_at = _now()
        self.error_type = None
        self.error_message = None

    def fail(self, error: Exception) -> None:
        self.status = QuoteExtractionRunStatus.FAILED
        self.completed_at = _now()
        self.error_type = type(error).__name__
        self.error_message = str(error)[:4000]

    def restart(self) -> None:
        if self.status is QuoteExtractionRunStatus.FAILED:
            self.status = QuoteExtractionRunStatus.QUEUED
            self.error_type = self.error_message = None
            self.completed_at = None


@dataclass(slots=True)
class QuoteItem:
    quote_id: UUID
    product_name: str
    quantity: Decimal | None
    unit_price: Decimal | None
    total_price: Decimal | None
    currency: str | None
    delivery_days: int | None
    technical_compliance: bool | None
    catalog_product_id: UUID | None = None
    extraction_run_id: UUID | None = None
    brand: str | None = None
    model: str | None = None
    unit: str | None = None
    description: str | None = None
    compliance_status: ComplianceStatus = ComplianceStatus.UNKNOWN
    match_status: MatchStatus = MatchStatus.UNMATCHED
    match_score: float = 0.0
    match_reason: str | None = None
    quoted_specifications: dict[str, str] = field(default_factory=dict)
    notes: str | None = None
    source_page: int | None = None
    evidence_fragment: str | None = None
    source_evidence_id: UUID | None = None
    confidence: float = 0.0
    warnings: tuple[str, ...] = ()
    original_extracted: dict[str, Any] = field(default_factory=dict)
    is_current: bool = True
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)

    def __post_init__(self) -> None:
        self.product_name = _clean(self.product_name, limit=500) or ""
        if not self.product_name:
            raise ValidationError("Quote item product name is required.")
        if self.quantity is not None:
            self.quantity = _decimal(self.quantity, "Quantity")
            if self.quantity == 0:
                raise ValidationError("Quote item quantity must be positive.")
        self.unit_price = _decimal(self.unit_price, "Unit price")
        self.total_price = _decimal(self.total_price, "Total price")
        self.currency = (_clean(self.currency, limit=3) or "").upper() or None
        if self.currency and (len(self.currency) != 3 or not self.currency.isalpha()):
            raise ValidationError("Quote item currency must be a three-letter code.")
        self.brand = _clean(self.brand, limit=255)
        self.model = _clean(self.model, limit=255)
        self.unit = _clean(self.unit, limit=50)
        self.description = _clean(self.description, limit=4000)
        self.notes = _clean(self.notes, limit=4000)
        self.evidence_fragment = _clean(self.evidence_fragment, limit=4000)
        if self.delivery_days is not None and self.delivery_days < 0:
            raise ValidationError("Delivery days cannot be negative.")
        if self.source_page is not None and self.source_page < 1:
            raise ValidationError("Quote evidence page must be positive.")
        if not 0 <= self.confidence <= 1 or not 0 <= self.match_score <= 1:
            raise ValidationError("Quote item confidence and match score must be between zero and one.")
        # Never synthesize total_price from quantity * unit_price: missing values remain unknown.
        self.technical_compliance = (
            True if self.compliance_status is ComplianceStatus.COMPLIANT
            else False if self.compliance_status is ComplianceStatus.NON_COMPLIANT
            else None
        )

    def apply_manual_correction(self, **changes: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        before = self.snapshot()
        allowed = {
            "catalog_product_id", "brand", "model", "unit", "quantity", "unit_price",
            "total_price", "currency", "delivery_days", "compliance_status", "notes",
        }
        for key, value in changes.items():
            if key not in allowed or value is None:
                continue
            setattr(self, key, value)
        self.__post_init__()
        self.updated_at = _now()
        return before, self.snapshot()

    def snapshot(self) -> dict[str, Any]:
        return {
            "catalog_product_id": str(self.catalog_product_id) if self.catalog_product_id else None,
            "brand": self.brand, "model": self.model, "unit": self.unit,
            "quantity": str(self.quantity) if self.quantity is not None else None,
            "unit_price": str(self.unit_price) if self.unit_price is not None else None,
            "total_price": str(self.total_price) if self.total_price is not None else None,
            "currency": self.currency, "delivery_days": self.delivery_days,
            "compliance_status": self.compliance_status.value, "notes": self.notes,
        }


@dataclass(frozen=True, slots=True)
class QuoteEvidenceReference:
    quote_document_id: UUID
    extraction_run_id: UUID
    field_name: str
    location_type: EvidenceLocationType
    location_label: str
    fragment: str
    method: str
    confidence: float
    quote_item_id: UUID | None = None
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=_now)

    def __post_init__(self) -> None:
        if not self.fragment.strip() or not self.field_name.strip() or not self.method.strip():
            raise ValidationError("Quote evidence requires field, fragment and extraction method.")
        if not 0 <= self.confidence <= 1:
            raise ValidationError("Evidence confidence must be between zero and one.")


@dataclass(frozen=True, slots=True)
class QuoteItemRevision:
    quote_item_id: UUID
    changed_by_user_id: UUID
    before: dict[str, Any]
    after: dict[str, Any]
    changed_fields: tuple[str, ...]
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=_now)


@dataclass(slots=True)
class QuoteTaskRecord:
    quote_id: UUID
    correlation_id: str
    id: UUID = field(default_factory=uuid4)
    status: QuoteTaskStatus = QuoteTaskStatus.QUEUED
    attempt_count: int = 0
    queued_at: datetime = field(default_factory=_now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_type: str | None = None
    error_message: str | None = None

    def start(self) -> None:
        self.status = QuoteTaskStatus.RUNNING
        self.attempt_count += 1
        self.started_at = _now()

    def complete(self) -> None:
        self.status = QuoteTaskStatus.COMPLETED
        self.completed_at = _now()
        self.error_type = self.error_message = None

    def fail(self, error: Exception) -> None:
        self.status = QuoteTaskStatus.FAILED
        self.completed_at = _now()
        self.error_type = type(error).__name__
        self.error_message = str(error)[:4000]
