from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, status

from app.api.dependencies import get_file_storage, get_quote_analysis_queue, get_uow_factory
from app.api.multipart import parse_document_upload, parse_quote_upload
from app.api.quote_schemas import (
    ComparisonGenerateRequestSchema,
    ComparisonResponseSchema,
    QuoteApprovalRequestSchema,
    QuoteDocumentsResponseSchema,
    QuoteEvidenceListResponseSchema,
    QuoteItemsResponseSchema,
    QuoteProcessingStatusResponseSchema,
    QuoteProcessRequestSchema,
    QuoteRejectionRequestSchema,
    QuoteResponseSchema,
    QuoteReviewRequestSchema,
    QuoteSubmitReviewRequestSchema,
    QuoteUploadResponseSchema,
    TenderQuotesResponseSchema,
    UpdateQuoteItemRequestSchema,
)
from app.api.schemas import ErrorResponseSchema
from app.application.dtos.quotes import (
    QuoteReviewCommand,
    UpdateQuoteItemCommand,
    UploadQuoteCommand,
    UploadQuoteDocumentCommand,
)
from app.application.ports.file_storage import FileStorage
from app.application.ports.quote_analysis_queue import QuoteAnalysisQueue
from app.application.ports.unit_of_work import UnitOfWorkFactory
from app.application.services.comparison_engine import ComparisonEngine
from app.application.use_cases.quotes import (
    AddQuoteDocument,
    ApproveQuote,
    GenerateTenderComparison,
    GetQuote,
    GetQuoteDocuments,
    GetQuoteEvidence,
    GetQuoteProcessingStatus,
    GetTenderComparison,
    ListTenderQuotes,
    QueueQuoteProcessing,
    RejectQuote,
    ReprocessQuote,
    ReviewQuote,
    SubmitQuoteForReview,
    UpdateQuoteItem,
)
from app.application.use_cases.tender_workflow import (
    UploadQuoteDocumentWorkflow,
    UploadSupplierQuoteWorkflow,
)
from app.config.settings import Settings, get_settings
from app.domain.documents.exceptions import InvalidDocumentFile
from app.domain.quotes.exceptions import InvalidQuoteState

router = APIRouter(tags=["quotes"])
UowFactoryDependency = Annotated[UnitOfWorkFactory, Depends(get_uow_factory)]
FileStorageDependency = Annotated[FileStorage, Depends(get_file_storage)]
QuoteQueueDependency = Annotated[QuoteAnalysisQueue, Depends(get_quote_analysis_queue)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]
ERROR_RESPONSES = {
    404: {"model": ErrorResponseSchema, "description": "Tender, supplier, quote, item or comparison not found"},
    409: {"model": ErrorResponseSchema, "description": "Invalid state or duplicate quote"},
    413: {"model": ErrorResponseSchema, "description": "Quote document exceeds configured limit"},
    422: {"model": ErrorResponseSchema, "description": "Invalid quote document or review payload"},
    503: {"model": ErrorResponseSchema, "description": "Storage, AI or queue unavailable"},
}


@router.post(
    "/tenders/{tender_id}/quotes",
    response_model=QuoteUploadResponseSchema,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Manually receive a supplier quote and queue analysis",
    responses=ERROR_RESPONSES,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "required": ["uploaded_by_user_id", "supplier_id", "files"],
                        "properties": {
                            "uploaded_by_user_id": {"type": "string", "format": "uuid"},
                            "supplier_id": {"type": "string", "format": "uuid"},
                            "rfq_request_id": {"type": "string", "format": "uuid"},
                            "files": {"type": "array", "maxItems": 1, "items": {"type": "string", "format": "binary"}},
                        },
                    }
                }
            },
        }
    },
)
async def upload_quote(
    tender_id: UUID,
    request: Request,
    uow_factory: UowFactoryDependency,
    file_storage: FileStorageDependency,
    queue: QuoteQueueDependency,
    settings: SettingsDependency,
    x_correlation_id: Annotated[str | None, Header(alias="X-Correlation-ID")] = None,
) -> QuoteUploadResponseSchema:
    uploaded_by_user_id, supplier_id, rfq_request_id, uploads = await parse_quote_upload(
        request,
        maximum_file_size_bytes=settings.max_quote_document_size_bytes,
    )
    if len(uploads) != 1:
        raise InvalidDocumentFile("Exactly one quote document is required.")
    result = UploadQuoteDocumentWorkflow(
        uow_factory,
        file_storage,
        queue,
        maximum_size_bytes=settings.max_quote_document_size_bytes,
    ).execute(
        UploadQuoteDocumentCommand(
            tender_id=tender_id,
            supplier_id=supplier_id,
            rfq_request_id=rfq_request_id,
            uploaded_by_user_id=uploaded_by_user_id,
            file=uploads[0],
            correlation_id=x_correlation_id,
        )
    )
    return QuoteUploadResponseSchema.model_validate(result, from_attributes=True)


@router.post(
    "/tenders/{tender_id}/suppliers/{tender_supplier_id}/quotes",
    response_model=QuoteResponseSchema,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Legacy supplier quote upload; supports PDF, XLSX and DOCX",
    responses=ERROR_RESPONSES,
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
        maximum_file_size_bytes=settings.max_quote_document_size_bytes,
        maximum_files=1,
    )
    if len(uploads) != 1:
        raise InvalidDocumentFile("Exactly one quote document is required.")
    result = UploadSupplierQuoteWorkflow(
        uow_factory,
        file_storage,
        queue,
        maximum_size_bytes=settings.max_quote_document_size_bytes,
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


@router.get("/tenders/{tender_id}/quotes", response_model=TenderQuotesResponseSchema)
def list_tender_quotes(tender_id: UUID, uow_factory: UowFactoryDependency) -> TenderQuotesResponseSchema:
    items = ListTenderQuotes(uow_factory).execute(tender_id)
    return TenderQuotesResponseSchema(
        items=tuple(QuoteResponseSchema.model_validate(item, from_attributes=True) for item in items),
        total=len(items),
    )


@router.get("/quotes/{quote_id}", response_model=QuoteResponseSchema, responses={404: ERROR_RESPONSES[404]})
def get_quote(quote_id: UUID, uow_factory: UowFactoryDependency) -> QuoteResponseSchema:
    return QuoteResponseSchema.model_validate(GetQuote(uow_factory).execute(quote_id), from_attributes=True)


@router.post("/quotes/{quote_id}/documents", response_model=QuoteDocumentsResponseSchema, status_code=status.HTTP_201_CREATED, responses=ERROR_RESPONSES)
async def add_quote_document(
    quote_id: UUID,
    request: Request,
    uow_factory: UowFactoryDependency,
    file_storage: FileStorageDependency,
    settings: SettingsDependency,
) -> QuoteDocumentsResponseSchema:
    uploader, uploads = await parse_document_upload(
        request,
        maximum_file_size_bytes=settings.max_quote_document_size_bytes,
        maximum_files=1,
    )
    if len(uploads) != 1:
        raise InvalidDocumentFile("Exactly one quote document is required.")
    AddQuoteDocument(
        uow_factory,
        file_storage,
        maximum_size_bytes=settings.max_quote_document_size_bytes,
    ).execute(quote_id, uploads[0], uploader)
    items = GetQuoteDocuments(uow_factory).execute(quote_id)
    return QuoteDocumentsResponseSchema(items=items, total=len(items))


@router.get("/quotes/{quote_id}/documents", response_model=QuoteDocumentsResponseSchema, responses={404: ERROR_RESPONSES[404]})
def list_quote_documents(quote_id: UUID, uow_factory: UowFactoryDependency) -> QuoteDocumentsResponseSchema:
    items = GetQuoteDocuments(uow_factory).execute(quote_id)
    return QuoteDocumentsResponseSchema(items=items, total=len(items))


@router.post("/quotes/{quote_id}/process", response_model=QuoteProcessingStatusResponseSchema, status_code=status.HTTP_202_ACCEPTED, responses=ERROR_RESPONSES)
def process_quote(
    quote_id: UUID,
    request: QuoteProcessRequestSchema,
    uow_factory: UowFactoryDependency,
    queue: QuoteQueueDependency,
) -> QuoteProcessingStatusResponseSchema:
    with uow_factory() as uow:
        if not uow.users.exists(request.requested_by_user_id):
            raise InvalidQuoteState("Quote processing user does not exist.")
    QueueQuoteProcessing(uow_factory, queue).execute(quote_id)
    return QuoteProcessingStatusResponseSchema.model_validate(
        GetQuoteProcessingStatus(uow_factory).execute(quote_id), from_attributes=True
    )


@router.get("/quotes/{quote_id}/processing-status", response_model=QuoteProcessingStatusResponseSchema, responses={404: ERROR_RESPONSES[404]})
def quote_processing_status(quote_id: UUID, uow_factory: UowFactoryDependency) -> QuoteProcessingStatusResponseSchema:
    return QuoteProcessingStatusResponseSchema.model_validate(
        GetQuoteProcessingStatus(uow_factory).execute(quote_id), from_attributes=True
    )


@router.get("/quotes/{quote_id}/items", response_model=QuoteItemsResponseSchema, responses={404: ERROR_RESPONSES[404]})
def quote_items(quote_id: UUID, uow_factory: UowFactoryDependency) -> QuoteItemsResponseSchema:
    quote = GetQuote(uow_factory).execute(quote_id)
    return QuoteItemsResponseSchema(items=quote.items, total=len(quote.items))


@router.patch("/quotes/{quote_id}/items/{item_id}", response_model=QuoteResponseSchema, responses=ERROR_RESPONSES)
def update_quote_item(
    quote_id: UUID,
    item_id: UUID,
    request: UpdateQuoteItemRequestSchema,
    uow_factory: UowFactoryDependency,
) -> QuoteResponseSchema:
    UpdateQuoteItem(uow_factory).execute(
        quote_id,
        item_id,
        UpdateQuoteItemCommand(
            changed_by_user_id=request.changed_by_user_id,
            catalog_product_id=request.catalog_product_id,
            product_name=request.product_name,
            description=request.description,
            brand=request.brand,
            model=request.model,
            quantity=request.quantity,
            unit=request.unit,
            unit_price=request.unit_price,
            total_price=request.total_price,
            currency=request.currency,
            delivery_days=request.delivery_days,
            compliance_status=request.compliance_status,
            notes=request.notes,
        ),
    )
    return QuoteResponseSchema.model_validate(GetQuote(uow_factory).execute(quote_id), from_attributes=True)


@router.get("/quotes/{quote_id}/evidence", response_model=QuoteEvidenceListResponseSchema, responses={404: ERROR_RESPONSES[404]})
def quote_evidence(quote_id: UUID, uow_factory: UowFactoryDependency) -> QuoteEvidenceListResponseSchema:
    items = GetQuoteEvidence(uow_factory).execute(quote_id)
    return QuoteEvidenceListResponseSchema(items=items, total=len(items))


@router.post("/quotes/{quote_id}/submit-review", response_model=QuoteResponseSchema, responses=ERROR_RESPONSES)
def submit_quote_review(
    quote_id: UUID,
    request: QuoteSubmitReviewRequestSchema,
    uow_factory: UowFactoryDependency,
) -> QuoteResponseSchema:
    return QuoteResponseSchema.model_validate(
        SubmitQuoteForReview(uow_factory).execute(quote_id, request.reviewer_user_id),
        from_attributes=True,
    )


@router.post("/quotes/{quote_id}/approve", response_model=QuoteResponseSchema, responses=ERROR_RESPONSES)
def approve_quote(
    quote_id: UUID,
    request: QuoteApprovalRequestSchema,
    uow_factory: UowFactoryDependency,
) -> QuoteResponseSchema:
    return QuoteResponseSchema.model_validate(
        ApproveQuote(uow_factory).execute(quote_id, request.reviewer_user_id),
        from_attributes=True,
    )


@router.post("/quotes/{quote_id}/reject", response_model=QuoteResponseSchema, responses=ERROR_RESPONSES)
def reject_quote(
    quote_id: UUID,
    request: QuoteRejectionRequestSchema,
    uow_factory: UowFactoryDependency,
) -> QuoteResponseSchema:
    return QuoteResponseSchema.model_validate(
        RejectQuote(uow_factory).execute(quote_id, request.reviewer_user_id, request.reason),
        from_attributes=True,
    )


@router.post("/quotes/{quote_id}/reprocess", response_model=QuoteProcessingStatusResponseSchema, status_code=status.HTTP_202_ACCEPTED, responses=ERROR_RESPONSES)
def reprocess_quote(
    quote_id: UUID,
    request: QuoteProcessRequestSchema,
    uow_factory: UowFactoryDependency,
    queue: QuoteQueueDependency,
) -> QuoteProcessingStatusResponseSchema:
    return QuoteProcessingStatusResponseSchema.model_validate(
        ReprocessQuote(uow_factory, queue).execute(quote_id, request.requested_by_user_id),
        from_attributes=True,
    )


@router.post("/quotes/{quote_id}/review", response_model=QuoteResponseSchema, responses=ERROR_RESPONSES)
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


@router.post("/tenders/{tender_id}/comparison", response_model=ComparisonResponseSchema, status_code=status.HTTP_201_CREATED, responses=ERROR_RESPONSES)
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


@router.get("/tenders/{tender_id}/comparison", response_model=ComparisonResponseSchema, responses={404: ERROR_RESPONSES[404]})
def get_comparison(tender_id: UUID, uow_factory: UowFactoryDependency) -> ComparisonResponseSchema:
    return ComparisonResponseSchema.model_validate(
        GetTenderComparison(uow_factory).execute(tender_id), from_attributes=True
    )
