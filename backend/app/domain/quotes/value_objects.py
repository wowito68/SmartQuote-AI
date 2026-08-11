from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum

from app.domain.shared.exceptions import ValidationError


class QuoteStatus(StrEnum):
    RECEIVED = "received"
    VALIDATING = "validating"
    READY_FOR_ANALYSIS = "ready_for_analysis"
    ANALYZING = "analyzing"
    ANALYZED = "analyzed"
    # Legacy states retained for already-persisted Iteration 9/12 records.
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
    CANCELLED = "cancelled"
    REUSED = "reused"


class QuoteDocumentType(StrEnum):
    PDF = "pdf"
    XLSX = "xlsx"
    DOCX = "docx"


class QuoteDocumentProcessingStatus(StrEnum):
    STORED = "stored"
    PROCESSING = "processing"
    PROCESSED = "processed"
    UNSUPPORTED = "unsupported"
    FAILED = "failed"


class ProductMatchStatus(StrEnum):
    MATCHED = "matched"
    POSSIBLE_MATCH = "possible_match"
    UNMATCHED = "unmatched"


class ComplianceStatus(StrEnum):
    COMPLIANT = "compliant"
    NON_COMPLIANT = "non_compliant"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


class EvidenceFindingStatus(StrEnum):
    FOUND = "found"
    NOT_FOUND = "not_found"
    INFERRED = "inferred"
    AMBIGUOUS = "ambiguous"


class QuoteTaskStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    RETRY_PENDING = "retry_pending"


class QuoteWarning(StrEnum):
    PRICE_CALCULATION_MISMATCH = "PRICE_CALCULATION_MISMATCH"
    PRICE_NOT_FOUND = "PRICE_NOT_FOUND"
    CURRENCY_UNKNOWN = "CURRENCY_UNKNOWN"
    QUANTITY_UNKNOWN = "QUANTITY_UNKNOWN"
    PRODUCT_UNMATCHED = "PRODUCT_UNMATCHED"
    POSSIBLE_PRODUCT_MATCH = "POSSIBLE_PRODUCT_MATCH"
    TECHNICAL_COMPLIANCE_UNKNOWN = "TECHNICAL_COMPLIANCE_UNKNOWN"
    TECHNICAL_NON_COMPLIANCE = "TECHNICAL_NON_COMPLIANCE"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    EVIDENCE_MISSING = "EVIDENCE_MISSING"


@dataclass(frozen=True, slots=True)
class Money:
    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        try:
            amount = Decimal(str(self.amount))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValidationError("Money amount is invalid.") from exc
        if not amount.is_finite() or amount < 0:
            raise ValidationError("Money amount must be non-negative and finite.")
        currency = self.currency.strip().upper()
        if len(currency) != 3 or not currency.isalpha():
            raise ValidationError("Money currency must be a three-letter code.")
        object.__setattr__(self, "amount", amount)
        object.__setattr__(self, "currency", currency)


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

    ALIASES = {
        "pza": "piece",
        "pzas": "piece",
        "pieza": "piece",
        "piezas": "piece",
        "pcs": "piece",
        "pc": "piece",
        "unidad": "piece",
        "unidades": "piece",
        "m": "meter",
        "metro": "meter",
        "metros": "meter",
        "kg": "kilogram",
        "kilogramo": "kilogram",
        "kilogramos": "kilogram",
        "l": "liter",
        "litro": "liter",
        "litros": "liter",
        "set": "set",
        "juego": "set",
        "service": "service",
        "servicio": "service",
    }

    def __post_init__(self) -> None:
        normalized = " ".join(self.value.strip().casefold().split())
        if not normalized:
            raise ValidationError("Unit is required.")
        object.__setattr__(self, "value", self.ALIASES.get(normalized, normalized))


@dataclass(frozen=True, slots=True)
class DeliveryTime:
    days: int

    def __post_init__(self) -> None:
        if self.days < 0:
            raise ValidationError("Delivery time cannot be negative.")


def confidence_band(value: float, *, high: float = 0.90, medium: float = 0.70) -> str:
    if not 0 <= value <= 1:
        raise ValidationError("Confidence must be between zero and one.")
    if not 0 <= medium <= high <= 1:
        raise ValueError("Confidence thresholds are invalid.")
    if value >= high:
        return "high"
    if value >= medium:
        return "medium"
    return "low"
