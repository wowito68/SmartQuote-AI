from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID, uuid4

from app.domain.quotes.exceptions import InvalidQuoteState
from app.domain.quotes.value_objects import (
    ComplianceStatus,
    EvidenceFindingStatus,
    ProductMatchStatus,
    QuoteDocumentProcessingStatus,
    QuoteDocumentType,
    QuoteExtractionRunStatus,
    QuoteStatus,
    QuoteTaskStatus,
    QuoteWarning,
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


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


_QUOTE_TRANSITIONS: dict[QuoteStatus, frozenset[QuoteStatus]] = {
    QuoteStatus.RECEIVED: frozenset({QuoteStatus.VALIDATING, QuoteStatus.REJECTED, QuoteStatus.FAILED}),
    QuoteStatus.VALIDATING: frozenset({QuoteStatus.EXTRACTING, QuoteStatus.FAILED}),
    QuoteStatus.EXTRACTING: frozenset({QuoteStatus.EXTRACTED, QuoteStatus.FAILED}),
    QuoteStatus.EXTRACTED: frozenset({QuoteStatus.NORMALIZED, QuoteStatus.FAILED}),
    QuoteStatus.NORMALIZED: frozenset({QuoteStatus.PENDING_REVIEW, QuoteStatus.FAILED}),
    QuoteStatus.PENDING_REVIEW: frozenset(
        {QuoteStatus.APPROVED, QuoteStatus.REJECTED, QuoteStatus.VALIDATING}
    ),
    QuoteStatus.APPROVED: frozenset({QuoteStatus.INCLUDED_IN_COMPARISON}),
    QuoteStatus.REJECTED: frozenset({QuoteStatus.VALIDATING}),
    QuoteStatus.FAILED: frozenset({QuoteStatus.VALIDATING, QuoteStatus.REJECTED}),
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
    status: QuoteStatus = QuoteStatus.RECEIVED
    currency: str | None = None
    subtotal_amount: Decimal | None = None
    tax_amount: Decimal | None = None
    total_amount: Decimal | None = None
    delivery_time_days: int | None = None
    commercial_terms: str | None = None
    valid_until: datetime | None = None
    received_at: datetime = field(default_factory=_now)
    approved_extraction_run_id: UUID | None = None
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
        if self.currency is not None and (len(self.currency) != 3 or not self.currency.isalpha()):
            raise ValidationError("Quote currency must be a three-letter code.")
        self.subtotal_amount = _decimal(self.subtotal_amount, "Quote subtotal")
        self.tax_amount = _decimal(self.tax_amount, "Quote tax")
        self.total_amount = _decimal(self.total_amount, "Quote total")
        if self.delivery_time_days is not None and self.delivery_time_days < 0:
            raise ValidationError("Quote delivery time cannot be negative.")
        self.commercial_terms = _clean(self.commercial_terms, limit=10000)
        self.received_at = _utc(self.received_at) or _now()
        self.valid_until = _utc(self.valid_until)
        self.created_at = _utc(self.created_at) or _now()
        self.updated_at = _utc(self.updated_at) or _now()
        self.reviewed_at = _utc(self.reviewed_at)

    def _transition(self, target: QuoteStatus) -> None:
        if target is self.status:
            return
        if target not in _QUOTE_TRANSITIONS[self.status]:
            raise InvalidQuoteState(
                f"Quote cannot transition from {self.status.value} to {target.value}."
            )
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

    def apply_summary(
        self,
        *,
        currency: str | None,
        subtotal_amount: Decimal | None,
        tax_amount: Decimal | None,
        total_amount: Decimal | None,
        delivery_time_days: int | None,
        commercial_terms: str | None,
        valid_until: datetime | None,
    ) -> None:
        if self.status is not QuoteStatus.EXTRACTED:
            raise InvalidQuoteState("Quote summary can only be normalized after extraction.")
        self.currency = (currency.strip().upper() if currency else None)
        self.subtotal_amount = _decimal(subtotal_amount, "Quote subtotal")
        self.tax_amount = _decimal(tax_amount, "Quote tax")
        self.total_amount = _decimal(total_amount, "Quote total")
        if delivery_time_days is not None and delivery_time_days < 0:
            raise ValidationError("Quote delivery time cannot be negative.")
        self.delivery_time_days = delivery_time_days
        self.commercial_terms = _clean(commercial_terms, limit=10000)
        self.valid_until = _utc(valid_until)
        self.mark_normalized()

    def mark_normalized(self) -> None:
        self._transition(QuoteStatus.NORMALIZED)

    def start_review(self) -> None:
        self._transition(QuoteStatus.PENDING_REVIEW)

    def approve(self, reviewer_user_id: UUID, extraction_run_id: UUID | None = None) -> None:
        self._transition(QuoteStatus.APPROVED)
        self.reviewed_by_user_id = reviewer_user_id
        self.reviewed_at = self.updated_at
        self.rejection_reason = None
        if extraction_run_id is not None:
            self.approved_extraction_run_id = extraction_run_id

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

    def restart_processing(self) -> None:
        if self.status in {QuoteStatus.APPROVED, QuoteStatus.INCLUDED_IN_COMPARISON}:
            raise InvalidQuoteState("Approved quotes cannot be reprocessed silently.")
        if self.status not in {QuoteStatus.PENDING_REVIEW, QuoteStatus.REJECTED, QuoteStatus.FAILED}:
            raise InvalidQuoteState("Quote is not eligible for reprocessing.")
        self._transition(QuoteStatus.VALIDATING)
        self.last_error = None

    def mark_failed(self, error: Exception | str) -> None:
        if self.status is QuoteStatus.FAILED:
            self.last_error = str(error)[:4000]
            self.updated_at = _now()
            return
        if QuoteStatus.FAILED not in _QUOTE_TRANSITIONS[self.status]:
            raise InvalidQuoteState("Quote cannot fail from its current state.")
        self._transition(QuoteStatus.FAILED)
        self.last_error = str(error)[:4000]

    def record_error(self, error: Exception) -> None:
        self.last_error = f"{type(error).__name__}: {error}"[:4000]
        self.updated_at = _now()


@dataclass(slots=True)
class QuoteDocument:
    quote_id: UUID
    storage_key: str
    original_file_name: str
    mime_type: str
    file_size: int
    file_hash: str
    document_type: QuoteDocumentType
    id: UUID = field(default_factory=uuid4)
    processing_status: QuoteDocumentProcessingStatus = QuoteDocumentProcessingStatus.STORED
    extractor_name: str | None = None
    extractor_version: str | None = None
    last_error: str | None = None
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)

    def __post_init__(self) -> None:
        if not _clean(self.storage_key, limit=1024) or not _clean(self.original_file_name, limit=255):
            raise ValidationError("Quote document file metadata is incomplete.")
        if self.file_size <= 0:
            raise ValidationError("Quote document size must be positive.")
        if len(self.file_hash) != 64:
            raise ValidationError("Quote document hash must be SHA-256.")

    def start_processing(self, extractor_name: str, extractor_version: str) -> None:
        if self.processing_status not in {
            QuoteDocumentProcessingStatus.STORED,
            QuoteDocumentProcessingStatus.FAILED,
        }:
            return
        self.processing_status = QuoteDocumentProcessingStatus.PROCESSING
        self.extractor_name = extractor_name
        self.extractor_version = extractor_version
        self.last_error = None
        self.updated_at = _now()

    def complete(self) -> None:
        self.processing_status = QuoteDocumentProcessingStatus.PROCESSED
        self.last_error = None
        self.updated_at = _now()

    def fail(self, error: Exception) -> None:
        self.processing_status = QuoteDocumentProcessingStatus.FAILED
        self.last_error = f"{type(error).__name__}: {error}"[:4000]
        self.updated_at = _now()


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
    quote_document_id: UUID | None = None
    provider: str = "openai"
    extractor_name: str = "unknown"
    extraction_fingerprint: str | None = None
    run_number: int = 1
    status: QuoteExtractionRunStatus = QuoteExtractionRunStatus.QUEUED
    provider_response_id: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: Decimal = Decimal("0")
    duration_ms: int | None = None
    raw_response: dict[str, Any] | None = None
    error_type: str | None = None
    error_message: str | None = None
    reused_from_run_id: UUID | None = None
    is_approved_source: bool = False
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime = field(default_factory=_now)

    def __post_init__(self) -> None:
        if len(self.idempotency_key) != 64 or len(self.schema_hash) != 64:
            raise ValidationError("Quote extraction keys must be SHA-256 digests.")
        if self.extraction_fingerprint is not None and len(self.extraction_fingerprint) != 64:
            raise ValidationError("Quote extraction fingerprint must be SHA-256.")
        for value in (
            self.extractor_version,
            self.prompt_version,
            self.model,
            self.schema_version,
            self.provider,
            self.extractor_name,
        ):
            if not value.strip():
                raise ValidationError("Quote extraction version metadata is required.")
        if self.run_number < 1:
            raise ValidationError("Quote extraction run number must be positive.")

    def start(self) -> None:
        if self.status in {QuoteExtractionRunStatus.COMPLETED, QuoteExtractionRunStatus.REUSED}:
            return
        self.status = QuoteExtractionRunStatus.RUNNING
        self.started_at = self.started_at or _now()
        self.completed_at = None
        self.error_type = None
        self.error_message = None

    def complete(
        self,
        *,
        provider_response_id: str | None,
        input_tokens: int,
        output_tokens: int,
        estimated_cost_usd: Decimal,
        raw_response: dict[str, Any],
        duration_ms: int | None = None,
    ) -> None:
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
            self.error_type = None
            self.error_message = None
            self.completed_at = None

    def mark_approved_source(self) -> None:
        self.is_approved_source = True


@dataclass(frozen=True, slots=True)
class QuoteEvidenceReference:
    quote_id: UUID
    quote_document_id: UUID
    extraction_run_id: UUID
    entity_type: str
    entity_id: UUID
    field_name: str
    locator_type: str
    locator: str
    fragment: str
    extraction_method: str
    finding_status: EvidenceFindingStatus
    confidence: float
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=_now)

    def __post_init__(self) -> None:
        if self.entity_type not in {"quote", "quote_item"}:
            raise ValidationError("Quote evidence entity type is invalid.")
        if not _clean(self.field_name, limit=100):
            raise ValidationError("Evidence field name is required.")
        if not _clean(self.locator_type, limit=30) or not _clean(self.locator, limit=255):
            raise ValidationError("Evidence locator is required.")
        if self.finding_status is EvidenceFindingStatus.FOUND and not _clean(self.fragment, limit=4000):
            raise ValidationError("Found evidence requires a source fragment.")
        if not 0 <= self.confidence <= 1:
            raise ValidationError("Evidence confidence must be between zero and one.")


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
    description: str | None = None
    brand: str | None = None
    model: str | None = None
    unit: str | None = None
    quoted_specifications: dict[str, str] = field(default_factory=dict)
    compliance_status: ComplianceStatus = ComplianceStatus.UNKNOWN
    match_status: ProductMatchStatus = ProductMatchStatus.UNMATCHED
    match_score: float = 0.0
    match_reason: str | None = None
    warnings: tuple[str, ...] = ()
    notes: str | None = None
    source_evidence_id: UUID | None = None
    source_page: int | None = None
    evidence_fragment: str | None = None
    confidence: float = 0.0
    original_extracted: dict[str, Any] = field(default_factory=dict)
    is_current: bool = True
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)

    def __post_init__(self) -> None:
        self.product_name = _clean(self.product_name, limit=500) or ""
        if not self.product_name:
            raise ValidationError("Quote item product name is required.")
        self.description = _clean(self.description, limit=4000)
        if self.quantity is not None:
            self.quantity = _decimal(self.quantity, "Quantity")
            if self.quantity == 0:
                raise ValidationError("Quote item quantity must be positive.")
        self.unit_price = _decimal(self.unit_price, "Unit price")
        self.total_price = _decimal(self.total_price, "Total price")
        self.currency = (_clean(self.currency, limit=3) or "").upper() or None
        if self.currency is not None and (len(self.currency) != 3 or not self.currency.isalpha()):
            raise ValidationError("Quote item currency must be a three-letter code.")
        self.brand = _clean(self.brand, limit=255)
        self.model = _clean(self.model, limit=255)
        self.unit = _clean(self.unit, limit=100)
        self.quoted_specifications = {
            _clean(str(key), limit=255) or "": _clean(str(value), limit=2000) or ""
            for key, value in self.quoted_specifications.items()
            if _clean(str(key)) and _clean(str(value))
        }
        self.notes = _clean(self.notes, limit=4000)
        self.evidence_fragment = _clean(self.evidence_fragment, limit=4000)
        self.match_reason = _clean(self.match_reason, limit=4000)
        if self.delivery_days is not None and self.delivery_days < 0:
            raise ValidationError("Delivery days cannot be negative.")
        if self.source_page is not None and self.source_page < 1:
            raise ValidationError("Quote evidence page must be positive.")
        if not 0 <= self.confidence <= 1 or not 0 <= self.match_score <= 1:
            raise ValidationError("Quote item scores must be between zero and one.")
        if self.compliance_status is ComplianceStatus.UNKNOWN:
            if self.technical_compliance is True:
                self.compliance_status = ComplianceStatus.COMPLIANT
            elif self.technical_compliance is False:
                self.compliance_status = ComplianceStatus.NON_COMPLIANT
        self.technical_compliance = (
            True
            if self.compliance_status is ComplianceStatus.COMPLIANT
            else False
            if self.compliance_status is ComplianceStatus.NON_COMPLIANT
            else None
        )
        self.warnings = tuple(dict.fromkeys(str(item) for item in self.warnings))
        self.original_extracted = dict(self.original_extracted)

    def recalculate_warnings(self, *, low_confidence_threshold: float = 0.70) -> None:
        warnings: list[str] = []
        if self.unit_price is None and self.total_price is None:
            warnings.append(QuoteWarning.PRICE_NOT_FOUND.value)
        if self.currency is None and (self.unit_price is not None or self.total_price is not None):
            warnings.append(QuoteWarning.CURRENCY_UNKNOWN.value)
        if self.quantity is None:
            warnings.append(QuoteWarning.QUANTITY_UNKNOWN.value)
        if self.match_status is ProductMatchStatus.UNMATCHED:
            warnings.append(QuoteWarning.PRODUCT_UNMATCHED.value)
        elif self.match_status is ProductMatchStatus.POSSIBLE_MATCH:
            warnings.append(QuoteWarning.POSSIBLE_PRODUCT_MATCH.value)
        if self.compliance_status is ComplianceStatus.UNKNOWN:
            warnings.append(QuoteWarning.TECHNICAL_COMPLIANCE_UNKNOWN.value)
        elif self.compliance_status is ComplianceStatus.NON_COMPLIANT:
            warnings.append(QuoteWarning.TECHNICAL_NON_COMPLIANCE.value)
        if self.confidence < low_confidence_threshold:
            warnings.append(QuoteWarning.LOW_CONFIDENCE.value)
        if (
            self.quantity is not None
            and self.unit_price is not None
            and self.total_price is not None
        ):
            expected = self.quantity * self.unit_price
            tolerance = max(Decimal("0.01"), abs(expected) * Decimal("0.001"))
            if abs(self.total_price - expected) > tolerance:
                warnings.append(QuoteWarning.PRICE_CALCULATION_MISMATCH.value)
        self.warnings = tuple(warnings)
        self.updated_at = _now()

    def apply_human_review(
        self,
        *,
        catalog_product_id: UUID | None,
        product_name: str | None,
        description: str | None,
        brand: str | None,
        model: str | None,
        quantity: Decimal | None,
        unit: str | None,
        unit_price: Decimal | None,
        total_price: Decimal | None,
        currency: str | None,
        delivery_days: int | None,
        compliance_status: ComplianceStatus | None,
        notes: str | None,
    ) -> None:
        self.catalog_product_id = catalog_product_id
        if product_name is not None:
            self.product_name = _clean(product_name, limit=500) or self.product_name
        if description is not None:
            self.description = _clean(description, limit=4000)
        if brand is not None:
            self.brand = _clean(brand, limit=255)
        if model is not None:
            self.model = _clean(model, limit=255)
        if quantity is not None:
            self.quantity = _decimal(quantity, "Quantity")
            if self.quantity == 0:
                raise ValidationError("Quote item quantity must be positive.")
        if unit is not None:
            self.unit = _clean(unit, limit=100)
        if unit_price is not None:
            self.unit_price = _decimal(unit_price, "Unit price")
        if total_price is not None:
            self.total_price = _decimal(total_price, "Total price")
        if currency is not None:
            normalized_currency = currency.strip().upper()
            if len(normalized_currency) != 3 or not normalized_currency.isalpha():
                raise ValidationError("Quote item currency must be a three-letter code.")
            self.currency = normalized_currency
        if delivery_days is not None:
            if delivery_days < 0:
                raise ValidationError("Delivery days cannot be negative.")
            self.delivery_days = delivery_days
        if compliance_status is not None:
            self.compliance_status = compliance_status
            self.technical_compliance = (
                True
                if compliance_status is ComplianceStatus.COMPLIANT
                else False
                if compliance_status is ComplianceStatus.NON_COMPLIANT
                else None
            )
        if notes is not None:
            self.notes = _clean(notes, limit=4000)
        self.updated_at = _now()

    def snapshot(self) -> dict[str, Any]:
        return {
            "catalog_product_id": str(self.catalog_product_id) if self.catalog_product_id else None,
            "product_name": self.product_name,
            "description": self.description,
            "brand": self.brand,
            "model": self.model,
            "quantity": str(self.quantity) if self.quantity is not None else None,
            "unit": self.unit,
            "unit_price": str(self.unit_price) if self.unit_price is not None else None,
            "total_price": str(self.total_price) if self.total_price is not None else None,
            "currency": self.currency,
            "delivery_days": self.delivery_days,
            "compliance_status": self.compliance_status.value,
            "notes": self.notes,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class QuoteItemRevision:
    quote_id: UUID
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
    task_name: str = "smartquote.quotes.analyze"
    id: UUID = field(default_factory=uuid4)
    status: QuoteTaskStatus = QuoteTaskStatus.QUEUED
    attempt_count: int = 0
    force_reprocess: bool = False
    last_error: str | None = None
    queued_at: datetime = field(default_factory=_now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    updated_at: datetime = field(default_factory=_now)

    def start(self) -> None:
        self.status = QuoteTaskStatus.RUNNING
        self.attempt_count += 1
        self.started_at = _now()
        self.updated_at = self.started_at
        self.last_error = None

    def succeed(self) -> None:
        self.status = QuoteTaskStatus.SUCCEEDED
        self.completed_at = _now()
        self.updated_at = self.completed_at
        self.last_error = None

    def fail(self, error: Exception, *, retryable: bool) -> None:
        self.status = (
            QuoteTaskStatus.RETRY_PENDING if retryable else QuoteTaskStatus.FAILED
        )
        self.last_error = f"{type(error).__name__}: {error}"[:4000]
        self.completed_at = _now() if not retryable else None
        self.updated_at = _now()
