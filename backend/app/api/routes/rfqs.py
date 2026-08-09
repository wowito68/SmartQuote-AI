from dataclasses import replace
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
    GenerateRfqRequestSchema,
    GenerateRfqsRequestSchema,
    RfqApprovalRequestSchema,
    RfqCancellationRequestSchema,
    RfqGenerationResponseSchema,
    RfqMessagesResponseSchema,
    RfqResponseSchema,
    RfqRetryRequestSchema,
    RfqReviewRejectionRequestSchema,
    RfqReviewRequestSchema,
    RfqSendRequestSchema,
    RfqVersionsResponseSchema,
    TenderRfqsResponseSchema,
    UpdateRfqRequestSchema,
)
from app.api.schemas import ErrorResponseSchema
from app.application.dtos.rfq_workflow import GenerateRfqCommand
from app.application.dtos.rfqs import CompanyProfile, GenerateRfqsCommand, UpdateRfqCommand
from app.application.ports.attachment_provider import AttachmentProvider
from app.application.ports.email_composer import EmailComposer
from app.application.ports.rfq_delivery_queue import RfqDeliveryQueue
from app.application.ports.unit_of_work import UnitOfWorkFactory
from app.application.use_cases.rfq_workflow import (
    ApproveRfqWorkflow,
    GenerateRfq,
    GetRfqVersions,
    QueueRfq,
    RejectRfq,
    RetryFailedRfq,
    SubmitRfqForReview,
    UpdateRfqWorkflow,
)
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
AttachmentProviderDependency = Annotated[AttachmentProvider, Depends(get_attachment_provider)]
EmailComposerDependency = Annotated[EmailComposer, Depends(get_email_composer)]
RfqQueueDependency = Annotated[RfqDeliveryQueue, Depends(get_rfq_delivery_queue)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]
ERROR_RESPONSES = {
    404: {"model": ErrorResponseSchema, "description": "Tender or RFQ not found"},
    409: {"model": ErrorResponseSchema, "description": "Invalid RFQ state or duplicate send"},
    422: {"model": ErrorResponseSchema, "description": "Invalid RFQ or attachment data"},
    503: {"model": ErrorResponseSchema, "description": "Template, queue or email unavailable"},
}


def _company(settings: Settings) -> CompanyProfile:
    return CompanyProfile(
        name=settings.company_name,
        contact_name=settings.company_contact_name,
        email=settings.company_email,
        phone=settings.company_phone,
    )


def _has_explicit_contact(uow_factory: UnitOfWorkFactory, rfq_id: UUID) -> bool:
    with uow_factory() as uow:
        rfq = uow.rfqs.get_rfq(rfq_id)
        return bool(rfq and rfq.contact_id)


@router.post(
    "/tenders/{tender_id}/rfqs",
    response_model=RfqResponseSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Generate one explicit RFQ draft",
    responses=ERROR_RESPONSES,
)
def generate_rfq(
    tender_id: UUID,
    request: GenerateRfqRequestSchema,
    uow_factory: UowFactoryDependency,
    composer: EmailComposerDependency,
    attachment_provider: AttachmentProviderDependency,
    settings: SettingsDependency,
) -> RfqResponseSchema:
    result = GenerateRfq(
        uow_factory,
        composer,
        attachment_provider,
        _company(settings),
    ).execute(
        GenerateRfqCommand(
            tender_id=tender_id,
            supplier_id=request.supplier_id,
            contact_id=request.contact_id,
            product_ids=request.product_ids,
            document_ids=request.document_ids,
            generated_by_user_id=request.generated_by_user_id,
            response_deadline=request.response_deadline,
            observations=request.observations,
            requested_currency=request.requested_currency,
            commercial_terms=request.commercial_terms,
            quote_validity=request.quote_validity,
            response_instructions=request.response_instructions,
            template_name=request.template_name,
            template_version=request.template_version,
        )
    )
    result = replace(result, contact_id=request.contact_id)
    return RfqResponseSchema.model_validate(result, from_attributes=True)


@router.post(
    "/tenders/{tender_id}/rfqs/generate",
    response_model=RfqGenerationResponseSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Generate legacy batch RFQs for approved suppliers",
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
        _company(settings),
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
    result = GetRfq(uow_factory).execute(rfq_id)
    with uow_factory() as uow:
        current = uow.rfqs.get_rfq(rfq_id)
        if current is not None:
            result = replace(result, contact_id=current.contact_id)
    return RfqResponseSchema.model_validate(result, from_attributes=True)


@router.put(
    "/rfqs/{rfq_id}",
    response_model=RfqResponseSchema,
    summary="Edit a legacy draft RFQ before approval",
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


@router.patch(
    "/rfqs/{rfq_id}",
    response_model=RfqResponseSchema,
    summary="Create a new editable RFQ version",
    responses=ERROR_RESPONSES,
)
def patch_rfq(
    rfq_id: UUID,
    request: UpdateRfqRequestSchema,
    uow_factory: UowFactoryDependency,
    attachment_provider: AttachmentProviderDependency,
) -> RfqResponseSchema:
    result = UpdateRfqWorkflow(uow_factory, attachment_provider).execute(
        rfq_id,
        UpdateRfqCommand(
            changed_by_user_id=request.changed_by_user_id,
            subject=request.subject,
            body=request.body,
            response_deadline=request.response_deadline,
            observations=request.observations,
            contact_name=request.contact_name,
            document_ids=request.document_ids,
        ),
        change_reason=request.change_reason,
    )
    return RfqResponseSchema.model_validate(result, from_attributes=True)


@router.post(
    "/rfqs/{rfq_id}/submit-review",
    response_model=RfqResponseSchema,
    summary="Submit a draft RFQ for human review",
    responses=ERROR_RESPONSES,
)
def submit_rfq_review(
    rfq_id: UUID,
    request: RfqReviewRequestSchema,
    uow_factory: UowFactoryDependency,
    attachment_provider: AttachmentProviderDependency,
) -> RfqResponseSchema:
    result = SubmitRfqForReview(uow_factory, attachment_provider).execute(
        rfq_id,
        request.reviewed_by_user_id,
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
    attachment_provider: AttachmentProviderDependency,
) -> RfqResponseSchema:
    if _has_explicit_contact(uow_factory, rfq_id):
        result = ApproveRfqWorkflow(uow_factory, attachment_provider).execute(
            rfq_id,
            request.approved_by_user_id,
        )
    else:
        result = ApproveRfq(uow_factory).execute(rfq_id, request.approved_by_user_id)
    return RfqResponseSchema.model_validate(result, from_attributes=True)


@router.post(
    "/rfqs/{rfq_id}/reject",
    response_model=RfqResponseSchema,
    summary="Reject an RFQ review and return it to draft",
    responses=ERROR_RESPONSES,
)
def reject_rfq(
    rfq_id: UUID,
    request: RfqReviewRejectionRequestSchema,
    uow_factory: UowFactoryDependency,
) -> RfqResponseSchema:
    result = RejectRfq(uow_factory).execute(
        rfq_id,
        request.reviewed_by_user_id,
        request.reason,
    )
    return RfqResponseSchema.model_validate(result, from_attributes=True)


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
    summary="Queue an explicitly approved RFQ for asynchronous delivery",
    responses=ERROR_RESPONSES,
)
def send_rfq(
    rfq_id: UUID,
    request: RfqSendRequestSchema,
    uow_factory: UowFactoryDependency,
    queue: RfqQueueDependency,
) -> RfqResponseSchema:
    if _has_explicit_contact(uow_factory, rfq_id):
        result = QueueRfq(uow_factory, queue).execute(rfq_id, request.requested_by_user_id)
    else:
        result = QueueRfqSend(uow_factory, queue).execute(
            rfq_id,
            request.requested_by_user_id,
        )
    return RfqResponseSchema.model_validate(result, from_attributes=True)


@router.post(
    "/rfqs/{rfq_id}/retry",
    response_model=RfqResponseSchema,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Retry a safely retryable failed RFQ",
    responses=ERROR_RESPONSES,
)
def retry_rfq(
    rfq_id: UUID,
    request: RfqRetryRequestSchema,
    uow_factory: UowFactoryDependency,
    queue: RfqQueueDependency,
) -> RfqResponseSchema:
    result = RetryFailedRfq(uow_factory, queue).execute(
        rfq_id,
        request.requested_by_user_id,
    )
    return RfqResponseSchema.model_validate(result, from_attributes=True)


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


@router.get(
    "/rfqs/{rfq_id}/versions",
    response_model=RfqVersionsResponseSchema,
    summary="List immutable RFQ content versions",
    responses={404: ERROR_RESPONSES[404]},
)
def get_rfq_versions(
    rfq_id: UUID,
    uow_factory: UowFactoryDependency,
) -> RfqVersionsResponseSchema:
    return RfqVersionsResponseSchema.model_validate(
        GetRfqVersions(uow_factory).execute(rfq_id),
        from_attributes=True,
    )
