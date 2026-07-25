from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum

from app.domain.shared.exceptions import ValidationError


class ProductStatus(StrEnum):
    CANDIDATE = "candidate"
    NORMALIZED = "normalized"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class AIExtractionRunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    REUSED = "reused"


@dataclass(frozen=True, slots=True)
class ConfidenceScore:
    value: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.value <= 1.0:
            raise ValidationError("Confidence must be between zero and one.")


@dataclass(frozen=True, slots=True)
class ProductQuantity:
    value: Decimal

    def __post_init__(self) -> None:
        if not self.value.is_finite() or self.value <= 0:
            raise ValidationError("Product quantity must be positive and finite.")

    @classmethod
    def from_value(cls, value: object) -> "ProductQuantity":
        try:
            normalized = Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise ValidationError("Product quantity is invalid.") from exc
        return cls(normalized)
