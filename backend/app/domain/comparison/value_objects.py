from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from app.domain.shared.exceptions import ValidationError


class ComparisonStatus(StrEnum):
    DRAFT = "draft"
    BUILDING = "building"
    READY = "ready"
    INVALID = "invalid"
    ARCHIVED = "archived"


class WarningSeverity(StrEnum):
    WARNING = "warning"
    CRITICAL = "critical"


class ComparisonWarningCode(StrEnum):
    MISSING_CURRENCY = "missing_currency"
    MISSING_PRICE = "missing_price"
    QUANTITY_MISMATCH = "quantity_mismatch"
    UNIT_MISMATCH = "unit_mismatch"
    PRODUCT_UNIDENTIFIED = "product_unidentified"
    COMPLIANCE_UNKNOWN = "compliance_unknown"
    DELIVERY_UNKNOWN = "delivery_unknown"
    DELIVERY_NOT_NORMALIZED = "delivery_not_normalized"
    DUPLICATE_QUOTE_ITEM = "duplicate_quote_item"
    SUPPLIER_WITHOUT_VALID_QUOTE = "supplier_without_valid_quote"
    INCOMPLETE_QUOTE = "incomplete_quote"
    MISSING_PRODUCT_QUOTE = "missing_product_quote"
    CURRENCY_MISMATCH = "currency_mismatch"
    REQUESTED_QUANTITY_UNKNOWN = "requested_quantity_unknown"
    REQUESTED_UNIT_UNKNOWN = "requested_unit_unknown"


class OfferStatus(StrEnum):
    QUOTED = "quoted"
    MISSING = "missing"
    INVALID = "invalid"


class MonetaryComparisonStatus(StrEnum):
    COMPARABLE = "comparable"
    REQUIRES_NORMALIZATION = "requires_normalization"
    INSUFFICIENT_DATA = "insufficient_data"


class QuantityComparisonStatus(StrEnum):
    MATCHED = "matched"
    QUANTITY_MISMATCH = "quantity_mismatch"
    UNIT_MISMATCH = "unit_mismatch"
    UNKNOWN = "unknown"


class NormalizedCompliance(StrEnum):
    COMPLIANT = "compliant"
    PARTIALLY_COMPLIANT = "partially_compliant"
    NON_COMPLIANT = "non_compliant"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class Money:
    amount: Decimal | None
    currency: str | None

    def __post_init__(self) -> None:
        if self.amount is not None and self.amount < 0:
            raise ValidationError("Money amount cannot be negative.")
        if self.currency is not None:
            normalized = self.currency.strip().upper()
            if len(normalized) != 3 or not normalized.isalpha():
                raise ValidationError("Currency must be a three-letter ISO-style code.")
            object.__setattr__(self, "currency", normalized)

    @property
    def is_complete(self) -> bool:
        return self.amount is not None and self.currency is not None


@dataclass(frozen=True, slots=True)
class Quantity:
    value: Decimal | None
    unit: str | None

    def __post_init__(self) -> None:
        if self.value is not None and self.value < 0:
            raise ValidationError("Quantity cannot be negative.")
        if self.unit is not None:
            cleaned = " ".join(self.unit.split()).casefold()
            object.__setattr__(self, "unit", cleaned or None)

    @property
    def is_complete(self) -> bool:
        return self.value is not None and self.unit is not None


@dataclass(frozen=True, slots=True)
class DeliveryTime:
    days: int | None
    original_text: str | None = None
    normalized: bool = True

    def __post_init__(self) -> None:
        if self.days is not None and self.days < 0:
            raise ValidationError("Delivery time cannot be negative.")
        if self.original_text is not None:
            cleaned = " ".join(self.original_text.split())
            object.__setattr__(self, "original_text", cleaned or None)
        if self.days is None and self.original_text:
            object.__setattr__(self, "normalized", False)

    @property
    def is_known(self) -> bool:
        return self.days is not None or self.original_text is not None
