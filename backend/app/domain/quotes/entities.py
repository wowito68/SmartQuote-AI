from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID, uuid4

from app.domain.quotes.exceptions import InvalidQuoteState
from app.domain.quotes.value_objects import QuoteExtractionRunStatus, QuoteStatus
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


def _money(value: Decimal | str | float | int | None, field_name: str) -> Decimal | None:
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
    QuoteStatus.RECEIVED: frozenset({QuoteStatus.VALIDATING}),
    QuoteStatus.VALIDATING: frozenset({QuoteStatus.EXTRACTING}),
    QuoteStatus.EXTRACTING: frozenset({QuoteStatus.EXTRACTED}),
    QuoteStatus.EXTRACTED: frozenset({QuoteStatus.NORMALIZED}),
    QuoteStatus.NORMALIZED: frozenset({QuoteStatus.PENDING_REVIEW}),
    QuoteStatus.PENDING_REVIEW: frozenset({QuoteStatus.APPROVED, QuoteStatus.REJECTED}),
    QuoteStatus.APPROVED: frozenset({QuoteStatus.INCLUDED_IN_COMPARISON}),
    QuoteStatus.REJECTED: frozenset(),
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

    def mark_normalized(self) -> None:
        self._transition(QuoteStatus.NORMALIZED)

    def start_review(self) -> None:
        self._transition(QuoteStatus.PENDING_REVIEW)

    def approve(self, reviewer_user_id: UUID) -> None:
        self._transition(QuoteStatus.APPROVED)
        self.reviewed_by_user_id = reviewer_user_id
        self.reviewed_at = self.updated_at
        self.rejection_reason = None

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

    def record_error(self, error: Exception) -> None:
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
    status: QuoteExtractionRunStatus = QuoteExtractionRunStatus.QUEUED
    provider_response_id: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: Decimal = Decimal("0")
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

    def complete(
        self,
        *,
        provider_response_id: str | None,
        input_tokens: int,
        output_tokens: int,
        estimated_cost_usd: Decimal,
        raw_response: dict[str, Any],
    ) -> None:
        self.status = QuoteExtractionRunStatus.COMPLETED
        self.provider_response_id = provider_response_id
        self.input_tokens = max(input_tokens, 0)
        self.output_tokens = max(output_tokens, 0)
        self.estimated_cost_usd = max(estimated_cost_usd, Decimal("0"))
        self.raw_response = raw_response
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
    brand: str | None = None
    model: str | None = None
    notes: str | None = None
    source_page: int | None = None
    evidence_fragment: str | None = None
    confidence: float = 0.0
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=_now)

    def __post_init__(self) -> None:
        self.product_name = _clean(self.product_name, limit=500) or ""
        if not self.product_name:
            raise ValidationError("Quote item product name is required.")
        if self.quantity is not None:
            self.quantity = _money(self.quantity, "Quantity")
            if self.quantity == 0:
                raise ValidationError("Quote item quantity must be positive.")
        self.unit_price = _money(self.unit_price, "Unit price")
        self.total_price = _money(self.total_price, "Total price")
        self.currency = (_clean(self.currency, limit=10) or "").upper() or None
        self.brand = _clean(self.brand, limit=255)
        self.model = _clean(self.model, limit=255)
        self.notes = _clean(self.notes, limit=4000)
        self.evidence_fragment = _clean(self.evidence_fragment, limit=4000)
        if self.delivery_days is not None and self.delivery_days < 0:
            raise ValidationError("Delivery days cannot be negative.")
        if self.source_page is not None and self.source_page < 1:
            raise ValidationError("Quote evidence page must be positive.")
        if not 0 <= self.confidence <= 1:
            raise ValidationError("Quote item confidence must be between zero and one.")
        if self.total_price is None and self.unit_price is not None and self.quantity is not None:
            self.total_price = self.unit_price * self.quantity
