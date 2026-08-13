from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from app.domain.recommendation.value_objects import RecommendationStatus


@dataclass(frozen=True, slots=True)
class RecommendationWeightsResponse:
    technical: Decimal
    price: Decimal
    delivery: Decimal


@dataclass(frozen=True, slots=True)
class RecommendationCandidateResponse:
    supplier_id: UUID
    supplier_name: str
    eligible: bool
    product_count: int
    technical_score: Decimal | None
    price_score: Decimal | None
    delivery_score: Decimal | None
    score: Decimal | None
    exclusion_reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RecommendationResponse:
    id: UUID
    comparison_id: UUID
    tender_id: UUID
    recommendation_key: str
    policy_version: str
    weights: RecommendationWeightsResponse
    generated_by_user_id: UUID
    status: RecommendationStatus
    candidates: tuple[RecommendationCandidateResponse, ...]
    recommended_supplier_id: UUID | None
    recommended_supplier_name: str | None
    explanation: str
    warnings: tuple[str, ...]
    human_review_required: bool
    created_at: datetime
