from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.api.catalog_schemas import (
    CatalogApprovalRequestSchema,
    CatalogExtractionRequestResponseSchema,
    CatalogExtractionRunResponseSchema,
    CatalogProductResponseSchema,
    CatalogProductUpdateRequestSchema,
    CatalogSnapshotResponseSchema,
    TenderCatalogResponseSchema,
)
from app.api.dependencies import get_ai_extraction_queue, get_prompt_registry, get_uow_factory
from app.api.schemas import ErrorResponseSchema
from app.application.ports.ai_extraction_queue import AIExtractionQueue
from app.application.ports.prompt_registry import PromptRegistry
from app.application.ports.unit_of_work import UnitOfWorkFactory
from app.application.use_cases.catalog import (
    ApproveTenderCatalog,
    GetCatalogProduct,
    GetTenderCatalog,
    RequestTenderCatalogExtraction,
    UpdateCatalogProduct,
)
from app.config.settings import Settings, get_settings

router = APIRouter(tags=["catalog"])
UowFactoryDependency = Annotated[UnitOfWorkFactory, Depends(get_uow_factory)]
AIQueueDependency = Annotated[AIExtractionQueue, Depends(get_ai_extraction_queue)]
PromptRegistryDependency = Annotated[PromptRegistry, Depends(get_prompt_registry)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]
ERROR_RESPONSES = {
    404: {"model": ErrorResponseSchema, "description": "Tender or catalog item not found"},
    409: {"model": ErrorResponseSchema, "description": "Invalid catalog state"},
    422: {"model": ErrorResponseSchema, "description": "Invalid review or extraction data"},
    503: {"model": ErrorResponseSchema, "description": "AI queue or provider unavailable"},
}


@router.post(
    "/tenders/{tender_id}/catalog/extract",
    response_model=CatalogExtractionRequestResponseSchema,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue AI catalog extraction for ready documents",
    responses=ERROR_RESPONSES,
)
def request_catalog_extraction(
    tender_id: UUID,
    uow_factory: UowFactoryDependency,
    ai_queue: AIQueueDependency,
    prompt_registry: PromptRegistryDependency,
    settings: SettingsDependency,
) -> CatalogExtractionRequestResponseSchema:
    result = RequestTenderCatalogExtraction(
        uow_factory,
        ai_queue,
        prompt_registry,
        prompt_version=settings.ai_prompt_version,
        model=settings.ai_model,
        temperature=settings.ai_temperature,
    ).execute(tender_id)
    return CatalogExtractionRequestResponseSchema(
        tender_id=result.tender_id,
        runs=[CatalogExtractionRunResponseSchema.model_validate(item) for item in result.runs],
        queued=result.queued,
        reused=result.reused,
    )


@router.get(
    "/tenders/{tender_id}/catalog",
    response_model=TenderCatalogResponseSchema,
    summary="Get tender catalog and review metrics",
    responses={404: ERROR_RESPONSES[404]},
)
def get_tender_catalog(
    tender_id: UUID,
    uow_factory: UowFactoryDependency,
) -> TenderCatalogResponseSchema:
    return TenderCatalogResponseSchema.model_validate(
        GetTenderCatalog(uow_factory).execute(tender_id), from_attributes=True
    )


@router.get(
    "/catalog/{product_id}",
    response_model=CatalogProductResponseSchema,
    summary="Get a catalog product with original extraction and evidence",
    responses={404: ERROR_RESPONSES[404]},
)
def get_catalog_product(
    product_id: UUID,
    uow_factory: UowFactoryDependency,
) -> CatalogProductResponseSchema:
    return CatalogProductResponseSchema.model_validate(
        GetCatalogProduct(uow_factory).execute(product_id), from_attributes=True
    )


@router.put(
    "/catalog/{product_id}",
    response_model=CatalogProductResponseSchema,
    summary="Edit, approve or reject a catalog product",
    responses=ERROR_RESPONSES,
)
def update_catalog_product(
    product_id: UUID,
    request: CatalogProductUpdateRequestSchema,
    uow_factory: UowFactoryDependency,
) -> CatalogProductResponseSchema:
    excluded = {"action", "reviewer_user_id", "rejection_reason"}
    changes = request.model_dump(exclude=excluded, exclude_unset=True)
    result = UpdateCatalogProduct(uow_factory).execute(
        product_id,
        action=request.action,
        reviewer_user_id=request.reviewer_user_id,
        changes=changes,
        rejection_reason=request.rejection_reason,
    )
    return CatalogProductResponseSchema.model_validate(result, from_attributes=True)


@router.post(
    "/tenders/{tender_id}/catalog/approve",
    response_model=CatalogSnapshotResponseSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Create an immutable approved catalog snapshot",
    responses=ERROR_RESPONSES,
)
def approve_tender_catalog(
    tender_id: UUID,
    request: CatalogApprovalRequestSchema,
    uow_factory: UowFactoryDependency,
) -> CatalogSnapshotResponseSchema:
    return CatalogSnapshotResponseSchema.model_validate(
        ApproveTenderCatalog(uow_factory).execute(tender_id, request.approved_by_user_id),
        from_attributes=True,
    )
