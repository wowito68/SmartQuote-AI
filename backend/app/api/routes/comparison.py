from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.api.comparison_schemas import (
    ComparisonGenerateRequestSchema,
    ComparisonResponseSchema,
)
from app.api.schemas import ErrorResponseSchema
from app.application.ports.unit_of_work import UnitOfWorkFactory
from app.application.services.comparison_builder import ComparisonBuilder
from app.application.use_cases.comparison import (
    GenerateTenderComparison,
    GetComparison,
    GetTenderComparison,
)
from app.config.settings import Settings, get_settings
from app.api.dependencies import get_uow_factory

router = APIRouter(tags=["comparisons"])
UowFactoryDependency = Annotated[UnitOfWorkFactory, Depends(get_uow_factory)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]
ERROR_RESPONSES = {
    404: {"model": ErrorResponseSchema, "description": "Tender or comparison not found"},
    409: {
        "model": ErrorResponseSchema,
        "description": "Approved catalog or approved quote prerequisites are missing",
    },
    422: {"model": ErrorResponseSchema, "description": "Invalid comparison request"},
}


@router.post(
    "/tenders/{tender_id}/comparisons",
    response_model=ComparisonResponseSchema,
    status_code=status.HTTP_201_CREATED,
    responses=ERROR_RESPONSES,
    summary="Build an auditable deterministic comparison from approved quotes",
)
def generate_comparison(
    tender_id: UUID,
    request: ComparisonGenerateRequestSchema,
    uow_factory: UowFactoryDependency,
    settings: SettingsDependency,
) -> ComparisonResponseSchema:
    result = GenerateTenderComparison(
        uow_factory,
        ComparisonBuilder(),
        comparison_rules_version=settings.comparison_rules_version,
    ).execute(tender_id, request.created_by_user_id)
    return ComparisonResponseSchema.model_validate(result, from_attributes=True)


@router.get(
    "/tenders/{tender_id}/comparisons",
    response_model=ComparisonResponseSchema,
    responses={404: ERROR_RESPONSES[404]},
    summary="Get the latest deterministic comparison for a tender",
)
def get_tender_comparison(
    tender_id: UUID,
    uow_factory: UowFactoryDependency,
) -> ComparisonResponseSchema:
    result = GetTenderComparison(uow_factory).execute(tender_id)
    return ComparisonResponseSchema.model_validate(result, from_attributes=True)


@router.get(
    "/comparisons/{comparison_id}",
    response_model=ComparisonResponseSchema,
    responses={404: ERROR_RESPONSES[404]},
    summary="Get a reproducible comparison by id",
)
def get_comparison(
    comparison_id: UUID,
    uow_factory: UowFactoryDependency,
) -> ComparisonResponseSchema:
    result = GetComparison(uow_factory).execute(comparison_id)
    return ComparisonResponseSchema.model_validate(result, from_attributes=True)
