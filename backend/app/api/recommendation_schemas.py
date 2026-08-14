from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from app.domain.recommendation.value_objects import RecommendationStatus


class RecommendationGenerateRequestSchema(BaseModel):
    generated_by_user_id: UUID = Field(
        validation_alias=AliasChoices("generated_by_user_id", "created_by_user_id")
    )
    technical_weight: Decimal = Field(ge=0, le=1)
    price_weight: Decimal = Field(ge=0, le=1)
    delivery_weight: Decimal = Field(ge=0, le=1)


class RecommendationWeightsSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    technical: Decimal
    price: Decimal
    delivery: Decimal


class RecommendationCandidateSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    supplier_id: UUID
    supplier_name: str
    eligible: bool
    product_count: int
    technical_score: Decimal | None
    price_score: Decimal | None
    delivery_score: Decimal | None
    score: Decimal | None
    exclusion_reasons: tuple[str, ...]


class RecommendationResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    comparison_id: UUID
    tender_id: UUID
    recommendation_key: str
    policy_version: str
    weights: RecommendationWeightsSchema
    generated_by_user_id: UUID
    status: RecommendationStatus
    candidates: tuple[RecommendationCandidateSchema, ...]
    recommended_supplier_id: UUID | None
    recommended_supplier_name: str | None
    explanation: str
    warnings: tuple[str, ...]
    human_review_required: bool
    created_at: datetime
