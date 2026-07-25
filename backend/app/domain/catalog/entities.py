from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from app.domain.catalog.exceptions import InvalidProductState
from app.domain.catalog.value_objects import (
    AIExtractionRunStatus,
    ConfidenceScore,
    ProductQuantity,
    ProductStatus,
)
from app.domain.shared.exceptions import ValidationError


def _now() -> datetime:
    return datetime.now(UTC)


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.split())
    return normalized or None


_PRODUCT_TRANSITIONS = {
    ProductStatus.CANDIDATE: {ProductStatus.NORMALIZED},
    ProductStatus.NORMALIZED: {ProductStatus.PENDING_REVIEW},
    ProductStatus.PENDING_REVIEW: {ProductStatus.APPROVED, ProductStatus.REJECTED},
    ProductStatus.APPROVED: set(),
    ProductStatus.REJECTED: set(),
}


@dataclass(slots=True)
class AIExtractionRun:
    tender_id: UUID
    document_id: UUID
    idempotency_key: str
    prompt_version: str
    model: str
    temperature: float
    schema_version: str
    schema_hash: str
    status: AIExtractionRunStatus = AIExtractionRunStatus.QUEUED
    id: UUID = field(default_factory=uuid4)
    provider_response_id: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: Decimal = Decimal("0")
    duration_ms: int | None = None
    products_detected: int = 0
    invalid_json_count: int = 0
    raw_response: dict[str, Any] | None = None
    validation_errors: list[str] = field(default_factory=list)
    error_type: str | None = None
    error_message: str | None = None
    reused_from_run_id: UUID | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime = field(default_factory=_now)

    def __post_init__(self) -> None:
        if len(self.idempotency_key) != 64 or len(self.schema_hash) != 64:
            raise ValidationError("AI extraction keys must be SHA-256 digests.")
        if (
            not self.prompt_version.strip()
            or not self.model.strip()
            or not self.schema_version.strip()
        ):
            raise ValidationError("Prompt version, model and schema version are required.")
        if not 0 <= self.temperature <= 2:
            raise ValidationError("Temperature must be between zero and two.")

    def start(self) -> None:
        if self.status is AIExtractionRunStatus.COMPLETED:
            return
        self.status = AIExtractionRunStatus.RUNNING
        self.started_at = _now()
        self.completed_at = None
        self.error_type = None
        self.error_message = None
        self.validation_errors = []

    def complete(
        self,
        *,
        provider_response_id: str | None,
        input_tokens: int,
        output_tokens: int,
        estimated_cost_usd: Decimal,
        duration_ms: int,
        products_detected: int,
        raw_response: dict[str, Any],
    ) -> None:
        self.status = AIExtractionRunStatus.COMPLETED
        self.provider_response_id = provider_response_id
        self.input_tokens = max(input_tokens, 0)
        self.output_tokens = max(output_tokens, 0)
        self.estimated_cost_usd = max(estimated_cost_usd, Decimal("0"))
        self.duration_ms = max(duration_ms, 0)
        self.products_detected = max(products_detected, 0)
        self.raw_response = raw_response
        self.completed_at = _now()
        self.error_type = None
        self.error_message = None

    def fail(self, error: Exception, *, validation_errors: list[str] | None = None) -> None:
        self.status = AIExtractionRunStatus.FAILED
        self.completed_at = _now()
        self.error_type = type(error).__name__
        self.error_message = str(error)[:4000]
        self.validation_errors = list(validation_errors or [])[:100]
        if self.validation_errors:
            self.invalid_json_count += 1

    def restart(self) -> None:
        self.status = AIExtractionRunStatus.QUEUED
        self.started_at = None
        self.completed_at = None
        self.error_type = None
        self.error_message = None
        self.validation_errors = []

    def mark_reused(self, source_run_id: UUID) -> None:
        self.status = AIExtractionRunStatus.REUSED
        self.reused_from_run_id = source_run_id
        self.completed_at = _now()
        self.duration_ms = 0


@dataclass(frozen=True, slots=True)
class EvidenceReference:
    evidence_id: UUID
    page_number: int
    x0: float | None = None
    y0: float | None = None
    x1: float | None = None
    y1: float | None = None
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        if self.page_number < 1:
            raise ValidationError("Evidence page number must be positive.")
        values = (self.x0, self.y0, self.x1, self.y1)
        if any(value is not None and value < 0 for value in values):
            raise ValidationError("Evidence coordinates cannot be negative.")
        if self.x0 is not None and self.x1 is not None and self.x1 < self.x0:
            raise ValidationError("Evidence x1 must be greater than or equal to x0.")
        if self.y0 is not None and self.y1 is not None and self.y1 < self.y0:
            raise ValidationError("Evidence y1 must be greater than or equal to y0.")


@dataclass(frozen=True, slots=True)
class ExtractedEvidence:
    product_id: UUID
    ai_extraction_run_id: UUID
    document_id: UUID
    page_number: int
    text_fragment: str
    confidence: ConfidenceScore
    model: str
    prompt_version: str
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=_now)

    def __post_init__(self) -> None:
        if self.page_number < 1:
            raise ValidationError("Evidence page number must be positive.")
        fragment = " ".join(self.text_fragment.split())
        if not fragment:
            raise ValidationError("Evidence text fragment is required.")
        object.__setattr__(self, "text_fragment", fragment[:4000])


@dataclass(slots=True)
class CatalogProduct:
    tender_id: UUID
    ai_extraction_run_id: UUID
    source_document_id: UUID
    original_payload: dict[str, Any]
    name: str
    confidence: ConfidenceScore
    description: str | None = None
    quantity: ProductQuantity | None = None
    unit: str | None = None
    category: str | None = None
    specifications: dict[str, str] = field(default_factory=dict)
    observations: str | None = None
    item_number: str | None = None
    status: ProductStatus = ProductStatus.CANDIDATE
    duplicate_of_product_id: UUID | None = None
    id: UUID = field(default_factory=uuid4)
    manual_edit_count: int = 0
    reviewed_by_user_id: UUID | None = None
    reviewed_at: datetime | None = None
    rejection_reason: str | None = None
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)

    def __post_init__(self) -> None:
        self.name = _clean(self.name) or ""
        if not self.name:
            raise ValidationError("Product name is required.")
        self.description = _clean(self.description)
        self.unit = _clean(self.unit)
        self.category = _clean(self.category)
        self.observations = _clean(self.observations)
        self.item_number = _clean(self.item_number)
        self.specifications = {
            _clean(key) or "": _clean(value) or ""
            for key, value in self.specifications.items()
            if _clean(key) and _clean(value)
        }

    def _transition(self, target: ProductStatus) -> None:
        if target is self.status:
            return
        if target not in _PRODUCT_TRANSITIONS[self.status]:
            raise InvalidProductState(
                f"Product cannot transition from {self.status.value} to {target.value}."
            )
        self.status = target
        self.updated_at = _now()

    def apply_normalization(
        self,
        *,
        name: str,
        description: str | None,
        quantity: Decimal | None,
        unit: str | None,
        category: str | None,
        specifications: dict[str, str],
        observations: str | None,
        duplicate_of_product_id: UUID | None = None,
    ) -> None:
        self.name = _clean(name) or self.name
        self.description = _clean(description)
        self.quantity = ProductQuantity(quantity) if quantity is not None else None
        self.unit = _clean(unit)
        self.category = _clean(category)
        self.specifications = specifications
        self.observations = _clean(observations)
        self.duplicate_of_product_id = duplicate_of_product_id
        self._transition(ProductStatus.NORMALIZED)

    def start_review(self) -> None:
        self._transition(ProductStatus.PENDING_REVIEW)

    def edit(
        self,
        *,
        reviewer_user_id: UUID,
        name: str | None = None,
        description: str | None = None,
        quantity: Decimal | None = None,
        unit: str | None = None,
        category: str | None = None,
        specifications: dict[str, str] | None = None,
        observations: str | None = None,
    ) -> None:
        if self.status is not ProductStatus.PENDING_REVIEW:
            raise InvalidProductState("Only pending-review products can be edited.")
        if name is not None:
            normalized_name = _clean(name)
            if not normalized_name:
                raise ValidationError("Product name cannot be empty.")
            self.name = normalized_name
        if description is not None:
            self.description = _clean(description)
        if quantity is not None:
            self.quantity = ProductQuantity(quantity)
        if unit is not None:
            self.unit = _clean(unit)
        if category is not None:
            self.category = _clean(category)
        if specifications is not None:
            self.specifications = {
                _clean(key) or "": _clean(value) or ""
                for key, value in specifications.items()
                if _clean(key) and _clean(value)
            }
        if observations is not None:
            self.observations = _clean(observations)
        self.manual_edit_count += 1
        self.reviewed_by_user_id = reviewer_user_id
        self.reviewed_at = _now()
        self.updated_at = self.reviewed_at

    def approve(self, reviewer_user_id: UUID) -> None:
        self._transition(ProductStatus.APPROVED)
        self.reviewed_by_user_id = reviewer_user_id
        self.reviewed_at = self.updated_at
        self.rejection_reason = None

    def reject(self, reviewer_user_id: UUID, reason: str) -> None:
        normalized_reason = _clean(reason)
        if not normalized_reason:
            raise ValidationError("A rejection reason is required.")
        self._transition(ProductStatus.REJECTED)
        self.reviewed_by_user_id = reviewer_user_id
        self.reviewed_at = self.updated_at
        self.rejection_reason = normalized_reason[:2000]

    def snapshot_payload(self) -> dict[str, Any]:
        return {
            "product_id": str(self.id),
            "item_number": self.item_number,
            "name": self.name,
            "description": self.description,
            "quantity": str(self.quantity.value) if self.quantity else None,
            "unit": self.unit,
            "category": self.category,
            "specifications": self.specifications,
            "observations": self.observations,
            "confidence": self.confidence.value,
            "source_document_id": str(self.source_document_id),
            "ai_extraction_run_id": str(self.ai_extraction_run_id),
        }


@dataclass(frozen=True, slots=True)
class CatalogSnapshot:
    tender_id: UUID
    version: int
    approved_by_user_id: UUID
    products: tuple[dict[str, Any], ...]
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=_now)

    def __post_init__(self) -> None:
        if self.version < 1:
            raise ValidationError("Catalog snapshot version must be positive.")
        if not self.products:
            raise ValidationError("An approved catalog must contain at least one product.")
