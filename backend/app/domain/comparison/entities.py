from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from app.domain.comparison.value_objects import (
    ComparisonStatus,
    ComparisonWarningCode,
    DeliveryTime,
    Money,
    MonetaryComparisonStatus,
    NormalizedCompliance,
    OfferStatus,
    Quantity,
    QuantityComparisonStatus,
    WarningSeverity,
)
from app.domain.shared.exceptions import ValidationError


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class ComparisonWarning:
    code: ComparisonWarningCode
    severity: WarningSeverity
    message: str
    supplier_id: UUID | None = None
    quote_id: UUID | None = None
    quote_item_id: UUID | None = None

    def __post_init__(self) -> None:
        cleaned = " ".join(self.message.split())
        if not cleaned:
            raise ValidationError("Comparison warning message is required.")
        object.__setattr__(self, "message", cleaned[:2000])

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code.value,
            "severity": self.severity.value,
            "message": self.message,
            "supplier_id": str(self.supplier_id) if self.supplier_id else None,
            "quote_id": str(self.quote_id) if self.quote_id else None,
            "quote_item_id": str(self.quote_item_id) if self.quote_item_id else None,
        }


@dataclass(frozen=True, slots=True)
class ComparisonOffer:
    supplier_id: UUID
    supplier_name: str
    status: OfferStatus
    quote_id: UUID | None = None
    quote_item_id: UUID | None = None
    quoted_product_name: str | None = None
    brand: str | None = None
    model: str | None = None
    quantity: Quantity = field(default_factory=lambda: Quantity(None, None))
    quantity_status: QuantityComparisonStatus = QuantityComparisonStatus.UNKNOWN
    unit_price: Money = field(default_factory=lambda: Money(None, None))
    total_price: Money = field(default_factory=lambda: Money(None, None))
    compliance: NormalizedCompliance = NormalizedCompliance.UNKNOWN
    delivery: DeliveryTime = field(default_factory=lambda: DeliveryTime(None))
    observations: str | None = None
    commercial_terms: str | None = None
    evidence_id: UUID | None = None
    confidence: float | None = None
    warnings: tuple[ComparisonWarning, ...] = ()
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        name = " ".join(self.supplier_name.split())
        if not name:
            raise ValidationError("Comparison offer supplier name is required.")
        object.__setattr__(self, "supplier_name", name[:500])
        if self.confidence is not None and not 0 <= self.confidence <= 1:
            raise ValidationError("Comparison offer confidence must be between zero and one.")
        if self.status is OfferStatus.MISSING and (
            self.quote_item_id is not None or self.quoted_product_name is not None
        ):
            raise ValidationError("Missing offers cannot reference a quote item.")

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "supplier_id": str(self.supplier_id),
            "supplier_name": self.supplier_name,
            "status": self.status.value,
            "quote_id": str(self.quote_id) if self.quote_id else None,
            "quote_item_id": str(self.quote_item_id) if self.quote_item_id else None,
            "quoted_product_name": self.quoted_product_name,
            "brand": self.brand,
            "model": self.model,
            "quantity": str(self.quantity.value) if self.quantity.value is not None else None,
            "unit": self.quantity.unit,
            "quantity_status": self.quantity_status.value,
            "unit_price": (
                str(self.unit_price.amount) if self.unit_price.amount is not None else None
            ),
            "total_price": (
                str(self.total_price.amount) if self.total_price.amount is not None else None
            ),
            "currency": self.unit_price.currency or self.total_price.currency,
            "compliance": self.compliance.value,
            "delivery_days": self.delivery.days,
            "delivery_original_text": self.delivery.original_text,
            "delivery_normalized": self.delivery.normalized,
            "observations": self.observations,
            "commercial_terms": self.commercial_terms,
            "evidence_id": str(self.evidence_id) if self.evidence_id else None,
            "confidence": self.confidence,
            "warnings": [warning.as_dict() for warning in self.warnings],
        }


@dataclass(frozen=True, slots=True)
class ComparisonItem:
    comparison_id: UUID
    product_id: UUID
    requested_product_name: str
    requested_quantity: Quantity
    offers: tuple[ComparisonOffer, ...]
    monetary_status: MonetaryComparisonStatus
    warnings: tuple[ComparisonWarning, ...] = ()
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=_now)

    def __post_init__(self) -> None:
        name = " ".join(self.requested_product_name.split())
        if not name:
            raise ValidationError("Requested product name is required for comparison.")
        object.__setattr__(self, "requested_product_name", name[:500])
        supplier_ids = [offer.supplier_id for offer in self.offers]
        if len(supplier_ids) != len(set(supplier_ids)):
            raise ValidationError("Comparison item can contain only one offer per supplier.")

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "product_id": str(self.product_id),
            "requested_product": self.requested_product_name,
            "requested_quantity": (
                str(self.requested_quantity.value)
                if self.requested_quantity.value is not None
                else None
            ),
            "requested_unit": self.requested_quantity.unit,
            "monetary_status": self.monetary_status.value,
            "offers": [offer.as_dict() for offer in self.offers],
            "warnings": [warning.as_dict() for warning in self.warnings],
        }


@dataclass(slots=True)
class Comparison:
    tender_id: UUID
    catalog_snapshot_id: UUID
    catalog_version: int
    quotes_version: str
    comparison_version: str
    comparison_key: str
    created_by_user_id: UUID
    source_quote_ids: tuple[UUID, ...]
    status: ComparisonStatus = ComparisonStatus.DRAFT
    items: tuple[ComparisonItem, ...] = ()
    warnings: tuple[ComparisonWarning, ...] = ()
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=_now)
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.catalog_version < 1:
            raise ValidationError("Catalog version must be positive.")
        if len(self.quotes_version) != 64 or len(self.comparison_key) != 64:
            raise ValidationError("Comparison version hashes must be SHA-256 digests.")
        if not self.comparison_version.strip():
            raise ValidationError("Comparison rules version is required.")

    def start(self) -> None:
        if self.status not in {ComparisonStatus.DRAFT, ComparisonStatus.BUILDING}:
            raise ValidationError("Only draft comparisons can start building.")
        self.status = ComparisonStatus.BUILDING
        self.completed_at = None

    def complete(
        self,
        items: tuple[ComparisonItem, ...],
        warnings: tuple[ComparisonWarning, ...],
    ) -> None:
        if self.status is not ComparisonStatus.BUILDING:
            raise ValidationError("Comparison must be building before completion.")
        if not items:
            raise ValidationError("Comparison must contain at least one product.")
        self.items = items
        self.warnings = warnings
        critical = any(
            warning.severity is WarningSeverity.CRITICAL
            for warning in warnings
        ) or any(
            warning.severity is WarningSeverity.CRITICAL
            for item in items
            for warning in item.warnings
        ) or any(
            warning.severity is WarningSeverity.CRITICAL
            for item in items
            for offer in item.offers
            for warning in offer.warnings
        )
        self.status = ComparisonStatus.INVALID if critical else ComparisonStatus.READY
        self.completed_at = _now()

    def archive(self) -> None:
        if self.status not in {ComparisonStatus.READY, ComparisonStatus.INVALID}:
            raise ValidationError("Only completed comparisons can be archived.")
        self.status = ComparisonStatus.ARCHIVED

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "tender_id": str(self.tender_id),
            "catalog_snapshot_id": str(self.catalog_snapshot_id),
            "catalog_version": self.catalog_version,
            "quotes_version": self.quotes_version,
            "comparison_version": self.comparison_version,
            "comparison_key": self.comparison_key,
            "status": self.status.value,
            "created_by_user_id": str(self.created_by_user_id),
            "source_quote_ids": [str(value) for value in self.source_quote_ids],
            "items": [item.as_dict() for item in self.items],
            "warnings": [warning.as_dict() for warning in self.warnings],
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
