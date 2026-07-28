from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.api.dependencies import (
    get_attachment_provider,
    get_email_composer,
    get_rfq_delivery_queue,
    get_uow_factory,
)
from app.api.rfq_schemas import (
    GenerateRfqsRequestSchema,
    RfqApprovalRequestSchema,
    RfqCancellationRequestSchema,
    RfqGenerationResponseSchema,
    RfqMessagesResponseSchema,
    RfqResponseSchema,
    RfqSendRequestSchema,
    TenderRfqsResponseSchema,
    UpdateRfqRequestSchema,
)
from app.api.schemas import ErrorResponseSchema
from app.application.dtos.rfqs import (
    CompanyProfile,
    GenerateRfqsCommand,
    UpdateRfqCommand,
)
from app.application.ports.attachment_provider import AttachmentProvider
from app.application.ports.email_composer import EmailComposer
from app.application.ports.rfq_delivery_queue import RfqDeliveryQueue
from app.application.ports.unit_of_work import UnitOfWorkFactory
from app.application.use_cases.rfqs import (
    ApproveRfq,
    CancelRfq,
    GenerateTenderRfqs,
    GetRfq,
    GetRfqMessages,
    GetTenderRfqs,
    QueueRfqSend,
    UpdateRfq,
)
from app.config.settings import Settings, get_settings

router = APIRouter(tags=["rfqs"])
UowFactoryDependency = Annotated[UnitOfWorkFactory, Depends(get_uow_factory)]
AttachmentProviderDependency = Annotated[
    AttachmentProvider, Depends(get_attachment_provider)
]
EmailComposerDependency = Annotated[EmailComposer, Depends(get_email_composer)]
RfqQueueDependency = Annotated[RfqDeliveryQueue, Depends(get_rfq_delivery_queue)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]
ERROR_RESPONSES = {
    404: {"model": ErrorResponseSchema, "description": "Tender or RFQ not found"},
    409: {"model": ErrorResponseSchema, "description": "Invalid RFQ state or duplicate send"},
    422: {"model": ErrorResponseSchema, "description": "Invalid RFQ or attachment data"},
    503: {"model": ErrorResponseSchema, "description": "Template, queue or email unavailable"},
}


@router.post(
    "/tenders/{tender_id}/rfqs/generate",
    response_model=RfqGenerationResponseSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Generate reviewable RFQ drafts for approved suppliers",
    responses=ERROR_RESPONSES,
)
def generate_rfqs(
    tender_id: UUID,
    request: GenerateRfqsRequestSchema,
    uow_factory: UowFactoryDependency,
    composer: EmailComposerDependency,
    attachment_provider: AttachmentProviderDependency,
    settings: SettingsDependency,
) -> RfqGenerationResponseSchema:
    result = GenerateTenderRfqs(
        uow_factory,
        composer,
        attachment_provider,
        CompanyProfile(
            name=settings.company_name,
            contact_name=settings.company_contact_name,
            email=settings.company_email,
            phone=settings.company_phone,
        ),
    ).execute(
        GenerateRfqsCommand(
            tender_id=tender_id,
            generated_by_user_id=request.generated_by_user_id,
            response_deadline=request.response_deadline,
            observations=request.observations,
            template_name=request.template_name,
            template_version=request.template_version,
            document_ids=request.document_ids,
        )
    )
    return RfqGenerationResponseSchema.model_validate(result, from_attributes=True)


@router.get(
    "/tenders/{tender_id}/rfqs",
    response_model=TenderRfqsResponseSchema,
    summary="List tender RFQs and delivery metrics",
    responses={404: ERROR_RESPONSES[404]},
)
def list_rfqs(
    tender_id: UUID,
    uow_factory: UowFactoryDependency,
) -> TenderRfqsResponseSchema:
    return TenderRfqsResponseSchema.model_validate(
        GetTenderRfqs(uow_factory).execute(tender_id), from_attributes=True
    )


@router.get(
    "/rfqs/{rfq_id}",
    response_model=RfqResponseSchema,
    summary="Get an RFQ draft, approval and delivery state",
    responses={404: ERROR_RESPONSES[404]},
)
def get_rfq(rfq_id: UUID, uow_factory: UowFactoryDependency) -> RfqResponseSchema:
    return RfqResponseSchema.model_validate(
        GetRfq(uow_factory).execute(rfq_id), from_attributes=True
    )


@router.put(
    "/rfqs/{rfq_id}",
    response_model=RfqResponseSchema,
    summary="Edit a draft RFQ before approval",
    responses=ERROR_RESPONSES,
)
def update_rfq(
    rfq_id: UUID,
    request: UpdateRfqRequestSchema,
    uow_factory: UowFactoryDependency,
    attachment_provider: AttachmentProviderDependency,
) -> RfqResponseSchema:
    result = UpdateRfq(uow_factory, attachment_provider).execute(
        rfq_id,
        UpdateRfqCommand(
            changed_by_user_id=request.changed_by_user_id,
            subject=request.subject,
            body=request.body,
            to_recipients=request.to_recipients,
            cc_recipients=request.cc_recipients,
            bcc_recipients=request.bcc_recipients,
            response_deadline=request.response_deadline,
            observations=request.observations,
            contact_name=request.contact_name,
            document_ids=request.document_ids,
        ),
    )
    return RfqResponseSchema.model_validate(result, from_attributes=True)


@router.post(
    "/rfqs/{rfq_id}/approve",
    response_model=RfqResponseSchema,
    summary="Approve and freeze an RFQ version",
    responses=ERROR_RESPONSES,
)
def approve_rfq(
    rfq_id: UUID,
    request: RfqApprovalRequestSchema,
    uow_factory: UowFactoryDependency,
) -> RfqResponseSchema:
    return RfqResponseSchema.model_validate(
        ApproveRfq(uow_factory).execute(rfq_id, request.approved_by_user_id),
        from_attributes=True,
    )


@router.post(
    "/rfqs/{rfq_id}/cancel",
    response_model=RfqResponseSchema,
    summary="Cancel an unsent RFQ",
    responses=ERROR_RESPONSES,
)
def cancel_rfq(
    rfq_id: UUID,
    request: RfqCancellationRequestSchema,
    uow_factory: UowFactoryDependency,
) -> RfqResponseSchema:
    return RfqResponseSchema.model_validate(
        CancelRfq(uow_factory).execute(
            rfq_id,
            request.cancelled_by_user_id,
            request.reason,
        ),
        from_attributes=True,
    )


@router.post(
    "/rfqs/{rfq_id}/send",
    response_model=RfqResponseSchema,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue an approved RFQ for asynchronous delivery",
    responses=ERROR_RESPONSES,
)
def send_rfq(
    rfq_id: UUID,
    request: RfqSendRequestSchema,
    uow_factory: UowFactoryDependency,
    queue: RfqQueueDependency,
) -> RfqResponseSchema:
    return RfqResponseSchema.model_validate(
        QueueRfqSend(uow_factory, queue).execute(rfq_id, request.requested_by_user_id),
        from_attributes=True,
    )


@router.get(
    "/rfqs/{rfq_id}/messages",
    response_model=RfqMessagesResponseSchema,
    summary="List outbound attempts and immutable delivery logs",
    responses={404: ERROR_RESPONSES[404]},
)
def get_rfq_messages(
    rfq_id: UUID,
    uow_factory: UowFactoryDependency,
) -> RfqMessagesResponseSchema:
    return RfqMessagesResponseSchema.model_validate(
        GetRfqMessages(uow_factory).execute(rfq_id), from_attributes=True
    )
