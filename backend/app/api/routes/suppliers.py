from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.api.dependencies import (
    get_supplier_discovery_queue,
    get_supplier_search_service,
    get_uow_factory,
)
from app.api.schemas import ErrorResponseSchema
from app.api.supplier_schemas import (
    ManualSupplierRequestSchema,
    SupplierApprovalRequestSchema,
    SupplierDiscoveryRequestResponseSchema,
    SupplierDiscoveryRequestSchema,
    SupplierMergeRequestSchema,
    SupplierRejectionRequestSchema,
    SupplierUpdateRequestSchema,
    TenderSupplierResponseSchema,
    TenderSuppliersResponseSchema,
)
from app.application.dtos.suppliers import (
    ManualSupplierCommand,
    SupplierUpdateCommand,
    SupplierUpdateContact,
)
from app.application.ports.supplier_discovery_queue import SupplierDiscoveryQueue
from app.application.ports.supplier_search_service import SupplierSearchService
from app.application.ports.unit_of_work import UnitOfWorkFactory
from app.application.services.supplier_deduplication import SupplierDeduplicationService
from app.application.services.supplier_matching import SupplierMatchingService
from app.application.use_cases.supplier_discovery import RequestSupplierDiscovery
from app.application.use_cases.suppliers import (
    ApproveSupplier,
    CreateManualSupplier,
    GetSupplier,
    GetTenderSuppliers,
    MergeSuppliers,
    RejectSupplier,
    UpdateSupplier,
)
from app.config.settings import Settings, get_settings

router = APIRouter(tags=["suppliers"])
UowFactoryDependency = Annotated[UnitOfWorkFactory, Depends(get_uow_factory)]
SupplierQueueDependency = Annotated[
    SupplierDiscoveryQueue, Depends(get_supplier_discovery_queue)
]
SupplierSearchDependency = Annotated[
    SupplierSearchService, Depends(get_supplier_search_service)
]
SettingsDependency = Annotated[Settings, Depends(get_settings)]
ERROR_RESPONSES = {
    404: {"model": ErrorResponseSchema, "description": "Tender or supplier not found"},
    409: {"model": ErrorResponseSchema, "description": "Invalid supplier state"},
    422: {"model": ErrorResponseSchema, "description": "Invalid supplier data"},
    503: {"model": ErrorResponseSchema, "description": "Search provider or queue unavailable"},
}


def _contact_commands(contacts) -> tuple[SupplierUpdateContact, ...]:
    return tuple(
        SupplierUpdateContact(
            contact_type=contact.contact_type,
            value=contact.value,
            confidence=contact.confidence,
            source_url=contact.source_url,
            contact_name=contact.contact_name,
            role=contact.role,
        )
        for contact in contacts
    )


@router.post(
    "/tenders/{tender_id}/suppliers/discover",
    response_model=SupplierDiscoveryRequestResponseSchema,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue supplier discovery for an approved catalog",
    responses=ERROR_RESPONSES,
)
def request_supplier_discovery(
    tender_id: UUID,
    request: SupplierDiscoveryRequestSchema,
    uow_factory: UowFactoryDependency,
    queue: SupplierQueueDependency,
    search_service: SupplierSearchDependency,
    settings: SettingsDependency,
) -> SupplierDiscoveryRequestResponseSchema:
    result = RequestSupplierDiscovery(
        uow_factory,
        queue,
        search_service,
        SupplierMatchingService(settings.supplier_matching_algorithm_version),
        search_configuration={
            "country": settings.supplier_search_country,
            "max_results_per_product": settings.supplier_search_max_results_per_product,
        },
    ).execute(tender_id, request.requested_by_user_id)
    return SupplierDiscoveryRequestResponseSchema.model_validate(
        result, from_attributes=True
    )


@router.get(
    "/tenders/{tender_id}/suppliers",
    response_model=TenderSuppliersResponseSchema,
    summary="List tender suppliers, evidence, matches and metrics",
    responses={404: ERROR_RESPONSES[404]},
)
def list_tender_suppliers(
    tender_id: UUID,
    uow_factory: UowFactoryDependency,
) -> TenderSuppliersResponseSchema:
    return TenderSuppliersResponseSchema.model_validate(
        GetTenderSuppliers(uow_factory).execute(tender_id), from_attributes=True
    )


@router.post(
    "/suppliers/merge",
    response_model=TenderSupplierResponseSchema,
    summary="Merge a duplicate supplier into a reviewed target",
    responses=ERROR_RESPONSES,
)
def merge_suppliers(
    request: SupplierMergeRequestSchema,
    uow_factory: UowFactoryDependency,
) -> TenderSupplierResponseSchema:
    result = MergeSuppliers(uow_factory).execute(
        request.source_tender_supplier_id,
        request.target_tender_supplier_id,
        request.reviewer_user_id,
        suggestion_id=request.suggestion_id,
    )
    return TenderSupplierResponseSchema.model_validate(result, from_attributes=True)


@router.post(
    "/suppliers/manual",
    response_model=TenderSupplierResponseSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Add a supplier manually to a tender",
    responses=ERROR_RESPONSES,
)
def create_manual_supplier(
    request: ManualSupplierRequestSchema,
    uow_factory: UowFactoryDependency,
) -> TenderSupplierResponseSchema:
    command = ManualSupplierCommand(
        tender_id=request.tender_id,
        created_by_user_id=request.created_by_user_id,
        legal_name=request.legal_name,
        trade_name=request.trade_name,
        website=request.website,
        category=request.category,
        country=request.country,
        city=request.city,
        description=request.description,
        contacts=_contact_commands(request.contacts),
        source_note=request.source_note,
    )
    result = CreateManualSupplier(
        uow_factory, SupplierDeduplicationService()
    ).execute(command)
    return TenderSupplierResponseSchema.model_validate(result, from_attributes=True)


@router.get(
    "/suppliers/{supplier_id}",
    response_model=TenderSupplierResponseSchema,
    summary="Get a tender supplier with global master data and evidence",
    responses={404: ERROR_RESPONSES[404]},
)
def get_supplier(
    supplier_id: UUID,
    uow_factory: UowFactoryDependency,
) -> TenderSupplierResponseSchema:
    return TenderSupplierResponseSchema.model_validate(
        GetSupplier(uow_factory).execute(supplier_id), from_attributes=True
    )


@router.put(
    "/suppliers/{supplier_id}",
    response_model=TenderSupplierResponseSchema,
    summary="Edit pending supplier master data and contacts",
    responses=ERROR_RESPONSES,
)
def update_supplier(
    supplier_id: UUID,
    request: SupplierUpdateRequestSchema,
    uow_factory: UowFactoryDependency,
) -> TenderSupplierResponseSchema:
    command = SupplierUpdateCommand(
        changed_by_user_id=request.changed_by_user_id,
        legal_name=request.legal_name,
        trade_name=request.trade_name,
        website=request.website,
        category=request.category,
        country=request.country,
        city=request.city,
        description=request.description,
        contacts=_contact_commands(request.contacts),
    )
    return TenderSupplierResponseSchema.model_validate(
        UpdateSupplier(uow_factory).execute(supplier_id, command), from_attributes=True
    )


@router.post(
    "/suppliers/{supplier_id}/approve",
    response_model=TenderSupplierResponseSchema,
    summary="Approve a tender supplier",
    responses=ERROR_RESPONSES,
)
def approve_supplier(
    supplier_id: UUID,
    request: SupplierApprovalRequestSchema,
    uow_factory: UowFactoryDependency,
) -> TenderSupplierResponseSchema:
    return TenderSupplierResponseSchema.model_validate(
        ApproveSupplier(uow_factory).execute(supplier_id, request.reviewer_user_id),
        from_attributes=True,
    )


@router.post(
    "/suppliers/{supplier_id}/reject",
    response_model=TenderSupplierResponseSchema,
    summary="Reject a tender supplier",
    responses=ERROR_RESPONSES,
)
def reject_supplier(
    supplier_id: UUID,
    request: SupplierRejectionRequestSchema,
    uow_factory: UowFactoryDependency,
) -> TenderSupplierResponseSchema:
    return TenderSupplierResponseSchema.model_validate(
        RejectSupplier(uow_factory).execute(
            supplier_id,
            request.reviewer_user_id,
            request.reason,
        ),
        from_attributes=True,
    )
