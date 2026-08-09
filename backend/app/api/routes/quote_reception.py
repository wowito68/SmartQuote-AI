from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, status

from app.api.dependencies import get_file_storage, get_quote_analysis_queue, get_uow_factory
from app.api.multipart import parse_document_upload
from app.api.quote_reception_schemas import (
    ProcessingStatusResponseSchema,
    QuoteDetailResponseSchema,
    QuoteDocumentsResponseSchema,
    QuoteItemsResponseSchema,
    QuoteItemUpdateSchema,
    QuoteProcessingRequestSchema,
    QuoteReviewActionSchema,
    QuoteUploadResponseSchema,
)
from app.application.dtos.quote_reception import (
    AddQuoteDocumentCommand,
    ReceiveQuoteCommand,
    UpdateQuoteItemCommand,
)
from app.application.ports.file_storage import FileStorage
from app.application.ports.quote_analysis_queue import QuoteAnalysisQueue
from app.application.ports.unit_of_work import UnitOfWorkFactory
from app.application.use_cases.quote_reception import (
    AddQuoteDocument,
    ApproveQuote,
    GetProcessingStatus,
    GetQuoteDetail,
    QueueQuoteProcessing,
    ReceiveQuote,
    RejectQuote,
    SubmitQuoteForReview,
    UpdateQuoteItem,
)
from app.config.settings import Settings, get_settings
from app.domain.documents.exceptions import InvalidDocumentFile
from app.domain.quotes.exceptions import InvalidQuoteState

router = APIRouter(tags=["quote-reception"])
UowFactoryDependency = Annotated[UnitOfWorkFactory, Depends(get_uow_factory)]
FileStorageDependency = Annotated[FileStorage, Depends(get_file_storage)]
QuoteQueueDependency = Annotated[QuoteAnalysisQueue, Depends(get_quote_analysis_queue)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]


@router.post(
    "/tenders/{tender_id}/quotes",
    response_model=QuoteUploadResponseSchema,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Receive one supplier quote manually and queue processing",
)
async def receive_quote(
    tender_id: UUID,
    request: Request,
    uow_factory: UowFactoryDependency,
    storage: FileStorageDependency,
    queue: QuoteQueueDependency,
    settings: SettingsDependency,
    tender_supplier_id: Annotated[UUID, Query()],
    rfq_request_id: Annotated[UUID | None, Query()] = None,
    x_correlation_id: Annotated[str | None, Header(alias="X-Correlation-ID")] = None,
) -> QuoteUploadResponseSchema:
    user_id, files = await parse_document_upload(
        request,
        maximum_file_size_bytes=settings.max_document_size_bytes,
        maximum_files=1,
    )
    if len(files) != 1:
        raise InvalidDocumentFile("Exactly one quote document is required.")
    result, duplicate = ReceiveQuote(
        uow_factory,
        storage,
        queue,
        maximum_size_bytes=settings.max_document_size_bytes,
    ).execute(
        ReceiveQuoteCommand(
            tender_id=tender_id,
            tender_supplier_id=tender_supplier_id,
            uploaded_by_user_id=user_id,
            file=files[0],
            rfq_request_id=rfq_request_id,
            correlation_id=x_correlation_id,
        )
    )
    return QuoteUploadResponseSchema(
        quote=QuoteDetailResponseSchema.model_validate(result, from_attributes=True),
        duplicate=duplicate,
    )


@router.get("/quotes/{quote_id}/review-detail", response_model=QuoteDetailResponseSchema)
def get_quote_review_detail(
    quote_id: UUID,
    uow_factory: UowFactoryDependency,
) -> QuoteDetailResponseSchema:
    return QuoteDetailResponseSchema.model_validate(
        GetQuoteDetail(uow_factory).execute(quote_id),
        from_attributes=True,
    )


@router.post(
    "/quotes/{quote_id}/documents",
    response_model=QuoteDocumentsResponseSchema,
    status_code=status.HTTP_201_CREATED,
)
async def add_quote_document(
    quote_id: UUID,
    request: Request,
    uow_factory: UowFactoryDependency,
    storage: FileStorageDependency,
    settings: SettingsDependency,
) -> QuoteDocumentsResponseSchema:
    user_id, files = await parse_document_upload(
        request,
        maximum_file_size_bytes=settings.max_document_size_bytes,
        maximum_files=1,
    )
    if len(files) != 1:
        raise InvalidDocumentFile("Exactly one quote document is required.")
    AddQuoteDocument(
        uow_factory,
        storage,
        maximum_size_bytes=settings.max_document_size_bytes,
    ).execute(
        AddQuoteDocumentCommand(
            quote_id=quote_id,
            uploaded_by_user_id=user_id,
            file=files[0],
        )
    )
    detail = GetQuoteDetail(uow_factory).execute(quote_id)
    return QuoteDocumentsResponseSchema(items=detail.documents, total=len(detail.documents))


@router.get("/quotes/{quote_id}/documents", response_model=QuoteDocumentsResponseSchema)
def list_quote_documents(
    quote_id: UUID,
    uow_factory: UowFactoryDependency,
) -> QuoteDocumentsResponseSchema:
    detail = GetQuoteDetail(uow_factory).execute(quote_id)
    return QuoteDocumentsResponseSchema(items=detail.documents, total=len(detail.documents))


@router.post(
    "/quotes/{quote_id}/process",
    response_model=ProcessingStatusResponseSchema,
    status_code=status.HTTP_202_ACCEPTED,
)
def process_quote(
    quote_id: UUID,
    payload: QuoteProcessingRequestSchema,
    uow_factory: UowFactoryDependency,
    queue: QuoteQueueDependency,
    x_correlation_id: Annotated[str | None, Header(alias="X-Correlation-ID")] = None,
) -> ProcessingStatusResponseSchema:
    with uow_factory() as uow:
        if not uow.users.exists(payload.requested_by_user_id):
            raise InvalidQuoteState("Processing requester user does not exist.")
    QueueQuoteProcessing(uow_factory, queue).execute(
        quote_id,
        x_correlation_id,
        force=False,
    )
    return ProcessingStatusResponseSchema.model_validate(
        GetProcessingStatus(uow_factory).execute(quote_id),
        from_attributes=True,
    )


@router.get("/quotes/{quote_id}/processing-status", response_model=ProcessingStatusResponseSchema)
def processing_status(
    quote_id: UUID,
    uow_factory: UowFactoryDependency,
) -> ProcessingStatusResponseSchema:
    return ProcessingStatusResponseSchema.model_validate(
        GetProcessingStatus(uow_factory).execute(quote_id),
        from_attributes=True,
    )


@router.get("/quotes/{quote_id}/items", response_model=QuoteItemsResponseSchema)
def quote_items(
    quote_id: UUID,
    uow_factory: UowFactoryDependency,
) -> QuoteItemsResponseSchema:
    detail = GetQuoteDetail(uow_factory).execute(quote_id)
    return QuoteItemsResponseSchema(items=detail.items, total=len(detail.items))


@router.patch("/quotes/{quote_id}/items/{item_id}", response_model=QuoteDetailResponseSchema)
def update_quote_item(
    quote_id: UUID,
    item_id: UUID,
    payload: QuoteItemUpdateSchema,
    uow_factory: UowFactoryDependency,
) -> QuoteDetailResponseSchema:
    result = UpdateQuoteItem(uow_factory).execute(
        quote_id,
        item_id,
        UpdateQuoteItemCommand(**payload.model_dump()),
    )
    return QuoteDetailResponseSchema.model_validate(result, from_attributes=True)


@router.post("/quotes/{quote_id}/submit-review", response_model=QuoteDetailResponseSchema)
def submit_quote_review(
    quote_id: UUID,
    payload: QuoteProcessingRequestSchema,
    uow_factory: UowFactoryDependency,
) -> QuoteDetailResponseSchema:
    result = SubmitQuoteForReview(uow_factory).execute(
        quote_id,
        payload.requested_by_user_id,
    )
    return QuoteDetailResponseSchema.model_validate(result, from_attributes=True)


@router.post("/quotes/{quote_id}/approve", response_model=QuoteDetailResponseSchema)
def approve_quote(
    quote_id: UUID,
    payload: QuoteReviewActionSchema,
    uow_factory: UowFactoryDependency,
) -> QuoteDetailResponseSchema:
    result = ApproveQuote(uow_factory).execute(quote_id, payload.reviewer_user_id)
    return QuoteDetailResponseSchema.model_validate(result, from_attributes=True)


@router.post("/quotes/{quote_id}/reject", response_model=QuoteDetailResponseSchema)
def reject_quote(
    quote_id: UUID,
    payload: QuoteReviewActionSchema,
    uow_factory: UowFactoryDependency,
) -> QuoteDetailResponseSchema:
    if not payload.reason:
        raise InvalidQuoteState("Quote rejection reason is required.")
    result = RejectQuote(uow_factory).execute(
        quote_id,
        payload.reviewer_user_id,
        payload.reason,
    )
    return QuoteDetailResponseSchema.model_validate(result, from_attributes=True)


@router.post(
    "/quotes/{quote_id}/reprocess",
    response_model=ProcessingStatusResponseSchema,
    status_code=status.HTTP_202_ACCEPTED,
)
def reprocess_quote(
    quote_id: UUID,
    payload: QuoteProcessingRequestSchema,
    uow_factory: UowFactoryDependency,
    queue: QuoteQueueDependency,
    x_correlation_id: Annotated[str | None, Header(alias="X-Correlation-ID")] = None,
) -> ProcessingStatusResponseSchema:
    with uow_factory() as uow:
        if not uow.users.exists(payload.requested_by_user_id):
            raise InvalidQuoteState("Reprocess requester user does not exist.")
    QueueQuoteProcessing(uow_factory, queue).execute(
        quote_id,
        x_correlation_id,
        force=True,
    )
    return ProcessingStatusResponseSchema.model_validate(
        GetProcessingStatus(uow_factory).execute(quote_id),
        from_attributes=True,
    )
