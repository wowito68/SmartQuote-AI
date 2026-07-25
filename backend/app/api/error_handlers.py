from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.application.exceptions import TenderCreatorNotFound, TenderNotFound
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
