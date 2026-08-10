from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, status

from app.api.dependencies import get_quote_analysis_queue, get_uow_factory
from app.api.quote_analysis_schemas import (
    QuoteAnalysisResponseSchema,
    QuoteAnalyzeRequestSchema,
)
from app.api.quote_schemas import QuoteProcessingStatusResponseSchema
from app.api.schemas import ErrorResponseSchema
from app.application.ports.quote_analysis_queue import QuoteAnalysisQueue
from app.application.ports.unit_of_work import UnitOfWorkFactory
from app.application.use_cases.quote_analysis import GetQuoteAnalysis, QueueQuoteAnalysis
from app.config.settings import Settings, get_settings

router = APIRouter(tags=["quote-analysis"])
UowFactoryDependency = Annotated[UnitOfWorkFactory, Depends(get_uow_factory)]
QuoteQueueDependency = Annotated[QuoteAnalysisQueue, Depends(get_quote_analysis_queue)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]
ERROR_RESPONSES = {
    404: {"model": ErrorResponseSchema, "description": "Quote was not found"},
    409: {"model": ErrorResponseSchema, "description": "Quote is not ready for analysis"},
    422: {"model": ErrorResponseSchema, "description": "Quote cannot be analyzed"},
    503: {"model": ErrorResponseSchema, "description": "Analysis queue is unavailable"},
}


@router.post(
    "/quotes/{quote_id}/analyze",
    response_model=QuoteProcessingStatusResponseSchema,
    status_code=status.HTTP_202_ACCEPTED,
    responses=ERROR_RESPONSES,
    summary="Start explicit asynchronous AI analysis of a received quote",
)
def analyze_quote(
    quote_id: UUID,
    request: QuoteAnalyzeRequestSchema,
    uow_factory: UowFactoryDependency,
    queue: QuoteQueueDependency,
    x_correlation_id: Annotated[
        str | None,
        Header(alias="X-Correlation-ID"),
    ] = None,
) -> QuoteProcessingStatusResponseSchema:
    result = QueueQuoteAnalysis(uow_factory, queue).execute(
        quote_id,
        request.requested_by_user_id,
        correlation_id=x_correlation_id,
    )
    return QuoteProcessingStatusResponseSchema.model_validate(
        result,
        from_attributes=True,
    )


@router.get(
    "/quotes/{quote_id}/analysis",
    response_model=QuoteAnalysisResponseSchema,
    responses={404: ERROR_RESPONSES[404]},
    summary="Get the latest structured quote analysis and review signals",
)
def get_quote_analysis(
    quote_id: UUID,
    uow_factory: UowFactoryDependency,
    settings: SettingsDependency,
) -> QuoteAnalysisResponseSchema:
    result = GetQuoteAnalysis(
        uow_factory,
        confidence_review_threshold=settings.quote_confidence_medium_threshold,
    ).execute(quote_id)
    return QuoteAnalysisResponseSchema.model_validate(result, from_attributes=True)


@router.post(
    "/quotes/{quote_id}/reanalyze",
    response_model=QuoteProcessingStatusResponseSchema,
    status_code=status.HTTP_202_ACCEPTED,
    responses=ERROR_RESPONSES,
    summary="Request a new versioned AI analysis for a quote",
)
def reanalyze_quote(
    quote_id: UUID,
    request: QuoteAnalyzeRequestSchema,
    uow_factory: UowFactoryDependency,
    queue: QuoteQueueDependency,
    x_correlation_id: Annotated[
        str | None,
        Header(alias="X-Correlation-ID"),
    ] = None,
) -> QuoteProcessingStatusResponseSchema:
    result = QueueQuoteAnalysis(uow_factory, queue).execute(
        quote_id,
        request.requested_by_user_id,
        force_reanalysis=True,
        correlation_id=x_correlation_id,
    )
    return QuoteProcessingStatusResponseSchema.model_validate(
        result,
        from_attributes=True,
    )
