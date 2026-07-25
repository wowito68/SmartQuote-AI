from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status

from app.api.dependencies import get_uow_factory
from app.api.schemas import (
    CreateTenderRequestSchema,
    ErrorResponseSchema,
    TenderListResponseSchema,
    TenderResponseSchema,
    UpdateTenderRequestSchema,
)
from app.application.dtos.tender import CreateTenderRequest, UpdateTenderRequest
from app.application.ports.unit_of_work import UnitOfWorkFactory
from app.application.use_cases.tenders import (
    ArchiveTender,
    CreateTender,
    GetTender,
    ListTenders,
    UpdateTender,
)

router = APIRouter(prefix="/tenders", tags=["tenders"])
UowFactoryDependency = Annotated[UnitOfWorkFactory, Depends(get_uow_factory)]
ERROR_RESPONSES = {
    404: {"model": ErrorResponseSchema, "description": "Tender not found"},
    409: {"model": ErrorResponseSchema, "description": "Business state conflict"},
    422: {"model": ErrorResponseSchema, "description": "Validation error"},
}


@router.post(
    "",
    response_model=TenderResponseSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Create a tender",
    responses={422: ERROR_RESPONSES[422]},
)
def create_tender(
    payload: CreateTenderRequestSchema,
    uow_factory: UowFactoryDependency,
) -> TenderResponseSchema:
    result = CreateTender(uow_factory).execute(
        CreateTenderRequest(
            title=payload.title,
            description=payload.description,
            deadline=payload.deadline,
            created_by_user_id=payload.created_by_user_id,
        )
    )
    return TenderResponseSchema.model_validate(result)


@router.get(
    "",
    response_model=TenderListResponseSchema,
    summary="List active tenders",
)
def list_tenders(uow_factory: UowFactoryDependency) -> TenderListResponseSchema:
    result = ListTenders(uow_factory).execute()
    return TenderListResponseSchema(
        items=[TenderResponseSchema.model_validate(item) for item in result.items],
        total=result.total,
    )


@router.get(
    "/{tender_id}",
    response_model=TenderResponseSchema,
    summary="Get a tender",
    responses={404: ERROR_RESPONSES[404], 422: ERROR_RESPONSES[422]},
)
def get_tender(tender_id: UUID, uow_factory: UowFactoryDependency) -> TenderResponseSchema:
    result = GetTender(uow_factory).execute(tender_id)
    return TenderResponseSchema.model_validate(result)


@router.put(
    "/{tender_id}",
    response_model=TenderResponseSchema,
    summary="Replace tender details",
    responses=ERROR_RESPONSES,
)
def update_tender(
    tender_id: UUID,
    payload: UpdateTenderRequestSchema,
    uow_factory: UowFactoryDependency,
) -> TenderResponseSchema:
    result = UpdateTender(uow_factory).execute(
        tender_id,
        UpdateTenderRequest(
            title=payload.title,
            description=payload.description,
            deadline=payload.deadline,
            status=payload.status,
        ),
    )
    return TenderResponseSchema.model_validate(result)


@router.delete(
    "/{tender_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Archive a tender",
    responses=ERROR_RESPONSES,
)
def archive_tender(tender_id: UUID, uow_factory: UowFactoryDependency) -> Response:
    ArchiveTender(uow_factory).execute(tender_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
