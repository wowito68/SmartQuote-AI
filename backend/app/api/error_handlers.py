from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.application.exceptions import TenderCreatorNotFound, TenderNotFound
from app.domain.documents.exceptions import (
    DocumentAlreadyDeleted,
    DocumentNotFound,
    DocumentStorageFailure,
    DocumentTooLarge,
    DocumentUploaderNotFound,
    DuplicateDocument,
    InvalidDocumentFile,
    TooManyDocuments,
)
from app.domain.shared.exceptions import ValidationError
from app.domain.tenders.exceptions import (
    InvalidDeadline,
    InvalidTenderState,
    TenderAlreadyArchived,
)


def _response(
    status_code: int,
    code: str,
    message: str,
    details: list[dict[str, Any]] | None = None,
) -> JSONResponse:
    payload: dict[str, object] = {"code": code, "message": message}
    if details is not None:
        payload["details"] = details
    return JSONResponse(status_code=status_code, content=payload)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(TenderNotFound)
    async def tender_not_found_handler(_: Request, exc: TenderNotFound) -> JSONResponse:
        return _response(status.HTTP_404_NOT_FOUND, "tender_not_found", str(exc))

    @app.exception_handler(TenderCreatorNotFound)
    async def creator_not_found_handler(
        _: Request,
        exc: TenderCreatorNotFound,
    ) -> JSONResponse:
        return _response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "tender_creator_not_found",
            str(exc),
        )

    @app.exception_handler(InvalidTenderState)
    async def invalid_state_handler(_: Request, exc: InvalidTenderState) -> JSONResponse:
        return _response(status.HTTP_409_CONFLICT, "invalid_tender_state", str(exc))

    @app.exception_handler(TenderAlreadyArchived)
    async def archived_handler(_: Request, exc: TenderAlreadyArchived) -> JSONResponse:
        return _response(status.HTTP_409_CONFLICT, "tender_already_archived", str(exc))

    @app.exception_handler(InvalidDeadline)
    async def invalid_deadline_handler(_: Request, exc: InvalidDeadline) -> JSONResponse:
        return _response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "invalid_deadline",
            str(exc),
        )

    @app.exception_handler(DocumentNotFound)
    async def document_not_found_handler(_: Request, exc: DocumentNotFound) -> JSONResponse:
        return _response(status.HTTP_404_NOT_FOUND, "document_not_found", str(exc))

    @app.exception_handler(DocumentAlreadyDeleted)
    async def document_deleted_handler(
        _: Request,
        exc: DocumentAlreadyDeleted,
    ) -> JSONResponse:
        return _response(status.HTTP_409_CONFLICT, "document_already_deleted", str(exc))

    @app.exception_handler(DuplicateDocument)
    async def duplicate_document_handler(_: Request, exc: DuplicateDocument) -> JSONResponse:
        return _response(status.HTTP_409_CONFLICT, "duplicate_document", str(exc))

    @app.exception_handler(DocumentTooLarge)
    async def document_too_large_handler(_: Request, exc: DocumentTooLarge) -> JSONResponse:
        return _response(status.HTTP_413_CONTENT_TOO_LARGE, "document_too_large", str(exc))

    @app.exception_handler(TooManyDocuments)
    async def too_many_documents_handler(_: Request, exc: TooManyDocuments) -> JSONResponse:
        return _response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "too_many_documents",
            str(exc),
        )

    @app.exception_handler(InvalidDocumentFile)
    async def invalid_document_handler(_: Request, exc: InvalidDocumentFile) -> JSONResponse:
        return _response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "invalid_document_file",
            str(exc),
        )

    @app.exception_handler(DocumentUploaderNotFound)
    async def uploader_not_found_handler(
        _: Request,
        exc: DocumentUploaderNotFound,
    ) -> JSONResponse:
        return _response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "document_user_not_found",
            str(exc),
        )

    @app.exception_handler(DocumentStorageFailure)
    async def storage_failure_handler(
        _: Request,
        exc: DocumentStorageFailure,
    ) -> JSONResponse:
        return _response(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "document_storage_unavailable",
            str(exc),
        )

    @app.exception_handler(ValidationError)
    async def validation_handler(_: Request, exc: ValidationError) -> JSONResponse:
        return _response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "validation_error",
            str(exc),
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(
        _: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        details = [
            {
                "location": list(error["loc"]),
                "message": error["msg"],
                "type": error["type"],
            }
            for error in exc.errors()
        ]
        return _response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "validation_error",
            "Request validation failed.",
            details,
        )
