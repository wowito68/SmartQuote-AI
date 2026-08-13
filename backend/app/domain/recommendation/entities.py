from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from app.domain.recommendation.value_objects import RecommendationStatus, RecommendationWeights
from app.domain.shared.exceptions import ValidationError


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class RecommendationCandidate:
    supplier_id: UUID
    supplier_name: str
    eligible: bool
    product_count: int
    technical_score: Decimal | None
    price_score: Decimal | None
    delivery_score: Decimal | None
    score: Decimal | None
    exclusion_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        name = " ".join(self.supplier_name.split())
        if not name:
            raise ValidationError("Recommendation candidate supplier name is required.")
        if self.product_count < 1:
            raise ValidationError("Recommendation candidate must cover at least one product.")
        if self.eligible and self.score is None:
            raise ValidationError("Eligible recommendation candidates require a score.")
        if not self.eligible and self.score is not None:
            raise ValidationError("Ineligible recommendation candidates cannot have a total score.")
        for value in (
            self.technical_score,
            self.price_score,
            self.delivery_score,
            self.score,
        ):
            if value is not None and (value < 0 or value > 100):
                raise ValidationError("Recommendation scores must be between zero and 100.")
        object.__setattr__(self, "supplier_name", name[:500])
        object.__setattr__(self, "exclusion_reasons", tuple(sorted(set(self.exclusion_reasons))))


@dataclass(frozen=True, slots=True)
class Recommendation:
    comparison_id: UUID
    tender_id: UUID
    recommendation_key: str
    policy_version: str
    weights: RecommendationWeights
    generated_by_user_id: UUID
    status: RecommendationStatus
    candidates: tuple[RecommendationCandidate, ...]
    recommended_supplier_id: UUID | None
    recommended_supplier_name: str | None
    explanation: str
    warnings: tuple[str, ...] = ()
    human_review_required: bool = True
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=_now)

    def __post_init__(self) -> None:
        if len(self.recommendation_key) != 64:
            raise ValidationError("Recommendation key must be a SHA-256 digest.")
        if not self.policy_version.strip():
            raise ValidationError("Recommendation policy version is required.")
        if not self.candidates:
            raise ValidationError("Recommendation requires at least one supplier candidate.")
        explanation = " ".join(self.explanation.split())
        if not explanation:
            raise ValidationError("Recommendation explanation is required.")
        if self.human_review_required is not True:
            raise ValidationError("Recommendation must explicitly require human review.")
        if self.status is RecommendationStatus.READY:
            if self.recommended_supplier_id is None or not self.recommended_supplier_name:
                raise ValidationError("Ready recommendations require a recommended supplier.")
            if not any(
                candidate.eligible and candidate.supplier_id == self.recommended_supplier_id
                for candidate in self.candidates
            ):
                raise ValidationError("Recommended supplier must be an eligible candidate.")
        elif self.recommended_supplier_id is not None or self.recommended_supplier_name is not None:
            raise ValidationError("Withheld recommendations cannot identify a supplier.")
        object.__setattr__(self, "policy_version", self.policy_version.strip()[:50])
        object.__setattr__(
            self,
            "recommended_supplier_name",
            (
                " ".join(self.recommended_supplier_name.split())[:500]
                if self.recommended_supplier_name
                else None
            ),
        )
        object.__setattr__(self, "explanation", explanation[:4000])
        object.__setattr__(self, "warnings", tuple(sorted(set(self.warnings))))
