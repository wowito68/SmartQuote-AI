from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum

from app.domain.shared.exceptions import ValidationError


class QuoteStatus(StrEnum):
    RECEIVED = "received"
    VALIDATING = "validating"
    EXTRACTING = "extracting"
    EXTRACTED = "extracted"
    NORMALIZED = "normalized"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    FAILED = "failed"
    INCLUDED_IN_COMPARISON = "included_in_comparison"


class QuoteExtractionRunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    REUSED = "reused"


class QuoteDocumentStatus(StrEnum):
    STORED = "stored"
    PROCESSING = "processing"
    EXTRACTED = "extracted"
    UNSUPPORTED = "unsupported"
    FAILED = "failed"


class MatchStatus(StrEnum):
    MATCHED = "matched"
    POSSIBLE_MATCH = "possible_match"
    UNMATCHED = "unmatched"


class ComplianceStatus(StrEnum):
    COMPLIANT = "compliant"
    NON_COMPLIANT = "non_compliant"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


class EvidenceLocationType(StrEnum):
    PAGE = "page"
    SHEET = "sheet"
    DOCUMENT = "document"


class QuoteTaskStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class Money:
    amount: Decimal
    currency: str | None = None

    def __post_init__(self) -> None:
        try:
            value = Decimal(str(self.amount))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValidationError("Money amount is invalid.") from exc
        if not value.is_finite() or value < 0:
            raise ValidationError("Money amount must be non-negative and finite.")
        object.__setattr__(self, "amount", value)
        if self.currency is not None:
            code = self.currency.strip().upper()
            if len(code) != 3 or not code.isalpha():
                raise ValidationError("Currency must be a three-letter code.")
            object.__setattr__(self, "currency", code)


@dataclass(frozen=True, slots=True)
class Quantity:
    value: Decimal

    def __post_init__(self) -> None:
        try:
            value = Decimal(str(self.value))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValidationError("Quantity is invalid.") from exc
        if not value.is_finite() or value <= 0:
            raise ValidationError("Quantity must be positive and finite.")
        object.__setattr__(self, "value", value)


@dataclass(frozen=True, slots=True)
class Unit:
    value: str

    def __post_init__(self) -> None:
        normalized = " ".join(self.value.split()).casefold()
        aliases = {
            "pza": "piece", "pieza": "piece", "piezas": "piece", "pcs": "piece",
            "pc": "piece", "unidad": "piece", "unidades": "piece", "ea": "piece",
            "kg": "kg", "kilogramo": "kg", "kilogramos": "kg",
            "m": "m", "metro": "m", "metros": "m",
            "l": "l", "litro": "l", "litros": "l",
        }
        normalized = aliases.get(normalized, normalized)
        if not normalized or len(normalized) > 50:
            raise ValidationError("Unit is invalid.")
        object.__setattr__(self, "value", normalized)


@dataclass(frozen=True, slots=True)
class DeliveryTime:
    days: int

    def __post_init__(self) -> None:
        if self.days < 0 or self.days > 3650:
            raise ValidationError("Delivery time is outside the supported range.")


HIGH_CONFIDENCE = 0.90
MEDIUM_CONFIDENCE = 0.70


def confidence_band(value: float) -> str:
    if not 0 <= value <= 1:
        raise ValidationError("Confidence must be between zero and one.")
    if value >= HIGH_CONFIDENCE:
        return "high"
    if value >= MEDIUM_CONFIDENCE:
        return "medium"
    return "low"
