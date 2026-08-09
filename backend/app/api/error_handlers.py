from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.application.exceptions import TenderCreatorNotFound, TenderNotFound
from app.domain.catalog.exceptions import (
    AIExtractionFailure,
    AIExtractionNotFound,
    AIResponseValidationError,
    CatalogProductNotFound,
    InvalidCatalogState,
    InvalidProductState,
    PromptNotFound,
)
from app.domain.documents.exceptions import (
    DocumentAlreadyDeleted,
    DocumentExtractionFailure,
    DocumentExtractionNotFound,
    DocumentNotFound,
    DocumentProcessingQueueFailure,
    DocumentQualityNotFound,
    DocumentStorageFailure,
    DocumentTooLarge,
    DocumentUploaderNotFound,
    DuplicateDocument,
    InvalidDocumentFile,
    InvalidDocumentState,
    TooManyDocuments,
)
from app.domain.quotes.exceptions import (
    ComparisonNotFound,
    ComparisonNotReady,
    DuplicateQuote,
    InvalidQuoteState,
    QuoteDocumentNotFound,
    QuoteExtractionFailure,
    QuoteItemNotFound,
    QuoteNotFound,
    QuoteProviderError,
    QuoteStorageError,
)
from app.domain.rfqs.exceptions import (
    AttachmentValidationError,
    DuplicateRfqSend,
    EmailCompositionError,
    EmailDeliveryError,
    EmailTemplateNotFound,
    InvalidRfqState,
    RfqGenerationError,
    RfqNotFound,
)
from app.domain.shared.exceptions import ValidationError
from app.domain.suppliers.exceptions import (
    InvalidSupplierDiscoveryState,
    InvalidSupplierState,
    SupplierDiscoveryNotFound,
    SupplierDiscoveryQueueFailure,
    SupplierMergeConflict,
    SupplierNotFound,
    SupplierSearchFailure,
)
from app.domain.tenders.exceptions import InvalidDeadline, InvalidTenderState, TenderAlreadyArchived


def _response(status_code: int, code: str, message: str, details: list[dict[str, Any]] | None = None) -> JSONResponse:
    payload: dict[str, object] = {"code": code, "message": message}
    if details is not None:
        payload["details"] = details
    return JSONResponse(status_code=status_code, content=payload)


def _exception_handler(status_code: int, code: str):
    async def handler(_: Request, exc: Exception) -> JSONResponse:
        return _response(status_code, code, str(exc))

    return handler


def register_exception_handlers(app: FastAPI) -> None:
    mappings = [
        (TenderNotFound, status.HTTP_404_NOT_FOUND, "tender_not_found"),
        (TenderCreatorNotFound, status.HTTP_422_UNPROCESSABLE_CONTENT, "tender_creator_not_found"),
        (InvalidTenderState, status.HTTP_409_CONFLICT, "invalid_tender_state"),
        (TenderAlreadyArchived, status.HTTP_409_CONFLICT, "tender_already_archived"),
        (InvalidDeadline, status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid_deadline"),
        (DocumentNotFound, status.HTTP_404_NOT_FOUND, "document_not_found"),
        (DocumentExtractionNotFound, status.HTTP_404_NOT_FOUND, "document_extraction_not_found"),
        (DocumentQualityNotFound, status.HTTP_404_NOT_FOUND, "document_quality_not_found"),
        (DocumentAlreadyDeleted, status.HTTP_409_CONFLICT, "document_already_deleted"),
        (DuplicateDocument, status.HTTP_409_CONFLICT, "duplicate_document"),
        (InvalidDocumentState, status.HTTP_409_CONFLICT, "invalid_document_state"),
        (DocumentTooLarge, status.HTTP_413_CONTENT_TOO_LARGE, "document_too_large"),
        (TooManyDocuments, status.HTTP_422_UNPROCESSABLE_CONTENT, "too_many_documents"),
        (InvalidDocumentFile, status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid_document_file"),
        (DocumentUploaderNotFound, status.HTTP_422_UNPROCESSABLE_CONTENT, "document_user_not_found"),
        (DocumentStorageFailure, status.HTTP_503_SERVICE_UNAVAILABLE, "document_storage_unavailable"),
        (DocumentProcessingQueueFailure, status.HTTP_503_SERVICE_UNAVAILABLE, "document_queue_unavailable"),
        (DocumentExtractionFailure, status.HTTP_503_SERVICE_UNAVAILABLE, "document_extraction_failed"),
        (CatalogProductNotFound, status.HTTP_404_NOT_FOUND, "catalog_product_not_found"),
        (AIExtractionNotFound, status.HTTP_404_NOT_FOUND, "ai_extraction_not_found"),
        (InvalidCatalogState, status.HTTP_409_CONFLICT, "invalid_catalog_state"),
        (InvalidProductState, status.HTTP_409_CONFLICT, "invalid_product_state"),
        (AIResponseValidationError, status.HTTP_422_UNPROCESSABLE_CONTENT, "ai_response_validation_error"),
        (AIExtractionFailure, status.HTTP_503_SERVICE_UNAVAILABLE, "ai_extraction_unavailable"),
        (PromptNotFound, status.HTTP_503_SERVICE_UNAVAILABLE, "prompt_not_found"),
        (SupplierNotFound, status.HTTP_404_NOT_FOUND, "supplier_not_found"),
        (SupplierDiscoveryNotFound, status.HTTP_404_NOT_FOUND, "supplier_discovery_not_found"),
        (InvalidSupplierState, status.HTTP_409_CONFLICT, "invalid_supplier_state"),
        (InvalidSupplierDiscoveryState, status.HTTP_409_CONFLICT, "invalid_supplier_discovery_state"),
        (SupplierMergeConflict, status.HTTP_409_CONFLICT, "supplier_merge_conflict"),
        (SupplierSearchFailure, status.HTTP_503_SERVICE_UNAVAILABLE, "supplier_search_unavailable"),
        (SupplierDiscoveryQueueFailure, status.HTTP_503_SERVICE_UNAVAILABLE, "supplier_queue_unavailable"),
        (RfqNotFound, status.HTTP_404_NOT_FOUND, "rfq_not_found"),
        (InvalidRfqState, status.HTTP_409_CONFLICT, "invalid_rfq_state"),
        (DuplicateRfqSend, status.HTTP_409_CONFLICT, "duplicate_rfq_send"),
        (RfqGenerationError, status.HTTP_409_CONFLICT, "rfq_generation_error"),
        (AttachmentValidationError, status.HTTP_422_UNPROCESSABLE_CONTENT, "rfq_attachment_invalid"),
        (EmailTemplateNotFound, status.HTTP_503_SERVICE_UNAVAILABLE, "email_template_not_found"),
        (EmailCompositionError, status.HTTP_503_SERVICE_UNAVAILABLE, "email_composition_failed"),
        (EmailDeliveryError, status.HTTP_503_SERVICE_UNAVAILABLE, "email_delivery_failed"),
        (QuoteNotFound, status.HTTP_404_NOT_FOUND, "quote_not_found"),
        (QuoteDocumentNotFound, status.HTTP_404_NOT_FOUND, "quote_document_not_found"),
        (QuoteItemNotFound, status.HTTP_404_NOT_FOUND, "quote_item_not_found"),
        (ComparisonNotFound, status.HTTP_404_NOT_FOUND, "comparison_not_found"),
        (DuplicateQuote, status.HTTP_409_CONFLICT, "duplicate_quote"),
        (InvalidQuoteState, status.HTTP_409_CONFLICT, "invalid_quote_state"),
        (ComparisonNotReady, status.HTTP_409_CONFLICT, "comparison_not_ready"),
        (QuoteStorageError, status.HTTP_503_SERVICE_UNAVAILABLE, "quote_storage_unavailable"),
        (QuoteProviderError, status.HTTP_503_SERVICE_UNAVAILABLE, "quote_provider_unavailable"),
        (QuoteExtractionFailure, status.HTTP_503_SERVICE_UNAVAILABLE, "quote_extraction_failed"),
        (ValidationError, status.HTTP_422_UNPROCESSABLE_CONTENT, "validation_error"),
    ]
    for exception_type, status_code, code in mappings:
        app.add_exception_handler(exception_type, _exception_handler(status_code, code))

    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {"location": list(error["loc"]), "message": error["msg"], "type": error["type"]}
            for error in exc.errors()
        ]
        return _response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "validation_error",
            "Request validation failed.",
            details,
        )
