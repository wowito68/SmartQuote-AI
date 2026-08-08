from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, status

from app.api.dependencies import (
    get_file_storage,
    get_quote_analysis_queue,
    get_uow_factory,
)
from app.api.multipart import parse_document_upload
from app.api.quote_schemas import (
    ComparisonGenerateRequestSchema,
    ComparisonResponseSchema,
    QuoteResponseSchema,
    QuoteReviewRequestSchema,
    TenderQuotesResponseSchema,
)
from app.api.schemas import ErrorResponseSchema
from app.application.dtos.quotes import QuoteReviewCommand, UploadQuoteCommand
from app.application.ports.file_storage import FileStorage
from app.application.ports.quote_analysis_queue import QuoteAnalysisQueue
from app.application.ports.unit_of_work import UnitOfWorkFactory
from app.application.services.comparison_engine import ComparisonEngine
from app.application.use_cases.quotes import (
    GenerateTenderComparison,
    GetQuote,
    GetTenderComparison,
    ListTenderQuotes,
    ReviewQuote,
    UploadSupplierQuote,
)
from app.config.settings import Settings, get_settings
from app.domain.documents.exceptions import InvalidDocumentFile

router = APIRouter(tags=["quotes"])
UowFactoryDependency = Annotated[UnitOfWorkFactory, Depends(get_uow_factory)]
FileStorageDependency = Annotated[FileStorage, Depends(get_file_storage)]
QuoteQueueDependency = Annotated[QuoteAnalysisQueue, Depends(get_quote_analysis_queue)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]
ERROR_RESPONSES = {
    404: {
        "model": ErrorResponseSchema,
        "description": "Tender, supplier, quote or comparison not found",
    },
    409: {"model": ErrorResponseSchema, "description": "Invalid state or duplicate quote"},
    413: {"model": ErrorResponseSchema, "description": "Quote PDF exceeds configured limit"},
    422: {"model": ErrorResponseSchema, "description": "Invalid quote PDF or review payload"},
    503: {"model": ErrorResponseSchema, "description": "Storage, AI or queue unavailable"},
}


@router.post(
    "/tenders/{tender_id}/suppliers/{tender_supplier_id}/quotes",
    response_model=QuoteResponseSchema,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload one supplier quote PDF and queue extraction",
    responses=ERROR_RESPONSES,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "required": ["uploaded_by_user_id", "files"],
                        "properties": {
                            "uploaded_by_user_id": {"type": "string", "format": "uuid"},
                            "files": {
                                "type": "array",
                                "maxItems": 1,
                                "items": {"type": "string", "format": "binary"},
                            },
                        },
                    }
                }
            },
        }
    },
)
async def upload_supplier_quote(
    tender_id: UUID,
    tender_supplier_id: UUID,
    request: Request,
    uow_factory: UowFactoryDependency,
    file_storage: FileStorageDependency,
    queue: QuoteQueueDependency,
    settings: SettingsDependency,
    x_correlation_id: Annotated[str | None, Header(alias="X-Correlation-ID")] = None,
) -> QuoteResponseSchema:
    uploaded_by_user_id, uploads = await parse_document_upload(
        request,
        maximum_file_size_bytes=settings.max_document_size_bytes,
        maximum_files=1,
    )
    if len(uploads) != 1:
        raise InvalidDocumentFile("Exactly one quote PDF is required.")
    result = UploadSupplierQuote(
        uow_factory,
        file_storage,
        queue,
        maximum_size_bytes=settings.max_document_size_bytes,
    ).execute(
        UploadQuoteCommand(
            tender_id=tender_id,
            tender_supplier_id=tender_supplier_id,
            uploaded_by_user_id=uploaded_by_user_id,
            file=uploads[0],
            correlation_id=x_correlation_id,
        )
    )
    return QuoteResponseSchema.model_validate(result, from_attributes=True)


@router.get(
    "/tenders/{tender_id}/quotes",
    response_model=TenderQuotesResponseSchema,
    summary="List supplier quotes for a tender",
    responses={404: ERROR_RESPONSES[404]},
)
def list_tender_quotes(
    tender_id: UUID,
    uow_factory: UowFactoryDependency,
) -> TenderQuotesResponseSchema:
    items = ListTenderQuotes(uow_factory).execute(tender_id)
    return TenderQuotesResponseSchema(
        items=tuple(
            QuoteResponseSchema.model_validate(item, from_attributes=True) for item in items
        ),
        total=len(items),
    )


@router.get(
    "/quotes/{quote_id}",
    response_model=QuoteResponseSchema,
    summary="Get quote extraction, normalization and review state",
    responses={404: ERROR_RESPONSES[404]},
)
def get_quote(quote_id: UUID, uow_factory: UowFactoryDependency) -> QuoteResponseSchema:
    return QuoteResponseSchema.model_validate(
        GetQuote(uow_factory).execute(quote_id), from_attributes=True
    )


@router.post(
    "/quotes/{quote_id}/review",
    response_model=QuoteResponseSchema,
    summary="Approve or reject a normalized supplier quote",
    responses=ERROR_RESPONSES,
)
def review_quote(
    quote_id: UUID,
    request: QuoteReviewRequestSchema,
    uow_factory: UowFactoryDependency,
) -> QuoteResponseSchema:
    result = ReviewQuote(uow_factory).execute(
        quote_id,
        QuoteReviewCommand(
            reviewer_user_id=request.reviewer_user_id,
            action=request.action,
            rejection_reason=request.rejection_reason,
        ),
    )
    return QuoteResponseSchema.model_validate(result, from_attributes=True)


@router.post(
    "/tenders/{tender_id}/comparison",
    response_model=ComparisonResponseSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Generate deterministic comparison and advisory recommendation",
    responses=ERROR_RESPONSES,
)
def generate_comparison(
    tender_id: UUID,
    request: ComparisonGenerateRequestSchema,
    uow_factory: UowFactoryDependency,
    settings: SettingsDependency,
) -> ComparisonResponseSchema:
    result = GenerateTenderComparison(
        uow_factory,
        ComparisonEngine(),
        scoring_config_version=settings.comparison_scoring_config_version,
    ).execute(tender_id, request.generated_by_user_id)
    return ComparisonResponseSchema.model_validate(result, from_attributes=True)


@router.get(
    "/tenders/{tender_id}/comparison",
    response_model=ComparisonResponseSchema,
    summary="Get latest deterministic tender comparison",
    responses={404: ERROR_RESPONSES[404]},
)
def get_comparison(
    tender_id: UUID,
    uow_factory: UowFactoryDependency,
) -> ComparisonResponseSchema:
    return ComparisonResponseSchema.model_validate(
        GetTenderComparison(uow_factory).execute(tender_id), from_attributes=True
    )
