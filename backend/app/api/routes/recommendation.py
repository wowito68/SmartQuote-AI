from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.api.dependencies import get_uow_factory
from app.api.recommendation_schemas import (
    RecommendationGenerateRequestSchema,
    RecommendationResponseSchema,
)
from app.api.schemas import ErrorResponseSchema
from app.application.ports.unit_of_work import UnitOfWorkFactory
from app.application.services.recommendation_engine import RecommendationEngine
from app.application.use_cases.recommendation import (
    GenerateRecommendation,
    GetLatestRecommendation,
    GetRecommendation,
)
from app.config.settings import Settings, get_settings
from app.domain.recommendation.value_objects import RecommendationWeights

router = APIRouter(tags=["recommendations"])
UowFactoryDependency = Annotated[UnitOfWorkFactory, Depends(get_uow_factory)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]
ERROR_RESPONSES = {
    404: {"model": ErrorResponseSchema, "description": "Comparison or recommendation not found"},
    409: {
        "model": ErrorResponseSchema,
        "description": "Comparison is not ready for a recommendation scenario",
    },
    422: {"model": ErrorResponseSchema, "description": "Invalid recommendation weights"},
}


@router.post(
    "/comparisons/{comparison_id}/recommendations",
    response_model=RecommendationResponseSchema,
    status_code=status.HTTP_201_CREATED,
    responses=ERROR_RESPONSES,
    summary="Generate or reuse an explainable recommendation scenario",
)
def generate_recommendation(
    comparison_id: UUID,
    request: RecommendationGenerateRequestSchema,
    uow_factory: UowFactoryDependency,
    settings: SettingsDependency,
) -> RecommendationResponseSchema:
    weights = RecommendationWeights(
        technical=request.technical_weight,
        price=request.price_weight,
        delivery=request.delivery_weight,
    )
    result = GenerateRecommendation(
        uow_factory,
        RecommendationEngine(),
        policy_version=settings.recommendation_policy_version,
    ).execute(comparison_id, request.generated_by_user_id, weights)
    return RecommendationResponseSchema.model_validate(result, from_attributes=True)


@router.get(
    "/comparisons/{comparison_id}/recommendations",
    response_model=RecommendationResponseSchema,
    responses={404: ERROR_RESPONSES[404]},
    summary="Get the latest recommendation scenario for a comparison",
)
def get_latest_recommendation(
    comparison_id: UUID,
    uow_factory: UowFactoryDependency,
) -> RecommendationResponseSchema:
    result = GetLatestRecommendation(uow_factory).execute(comparison_id)
    return RecommendationResponseSchema.model_validate(result, from_attributes=True)


@router.get(
    "/recommendations/{recommendation_id}",
    response_model=RecommendationResponseSchema,
    responses={404: ERROR_RESPONSES[404]},
    summary="Get a reproducible recommendation scenario by id",
)
def get_recommendation(
    recommendation_id: UUID,
    uow_factory: UowFactoryDependency,
) -> RecommendationResponseSchema:
    result = GetRecommendation(uow_factory).execute(recommendation_id)
    return RecommendationResponseSchema.model_validate(result, from_attributes=True)
