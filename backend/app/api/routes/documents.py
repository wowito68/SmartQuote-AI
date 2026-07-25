from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status

from app.api.dependencies import get_file_storage, get_uow_factory
from app.api.document_schemas import (
    TenderDocumentListResponseSchema,
    TenderDocumentResponseSchema,
)
from app.api.multipart import parse_document_upload
from app.api.schemas import ErrorResponseSchema
from app.application.dtos.document import (
    TenderDocumentListResponse,
    UploadTenderDocumentRequest,
)
from app.application.ports.file_storage import FileStorage
from app.application.ports.unit_of_work import UnitOfWorkFactory
from app.application.use_cases.documents import (
    DeleteTenderDocument,
    DownloadTenderDocument,
    GetTenderDocument,
    ListTenderDocuments,
    UploadTenderDocument,
)
from app.config.settings import Settings, get_settings

router = APIRouter(tags=["documents"])
UowFactoryDependency = Annotated[UnitOfWorkFactory, Depends(get_uow_factory)]
FileStorageDependency = Annotated[FileStorage, Depends(get_file_storage)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]
ERROR_RESPONSES = {
    404: {"model": ErrorResponseSchema, "description": "Tender or document not found"},
    409: {"model": ErrorResponseSchema, "description": "Duplicate or invalid state"},
    413: {"model": ErrorResponseSchema, "description": "File exceeds configured limit"},
    422: {"model": ErrorResponseSchema, "description": "Invalid document upload"},
    503: {"model": ErrorResponseSchema, "description": "Private storage unavailable"},
}


def _list_response(
    result: TenderDocumentListResponse,
) -> TenderDocumentListResponseSchema:
    return TenderDocumentListResponseSchema(
        items=[TenderDocumentResponseSchema.model_validate(item) for item in result.items],
        total=result.total,
    )


@router.post(
    "/tenders/{tender_id}/documents",
    response_model=TenderDocumentListResponseSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Upload one or more PDF documents",
    responses=ERROR_RESPONSES,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "required": ["uploaded_by_user_id", "files"],
                        "properties": {
                            "uploaded_by_user_id": {"type": "string", "format": "uuid"},
                            "files": {
                                "type": "array",
                                "items": {"type": "string", "format": "binary"},
                            },
                        },
                    }
                }
            },
        }
    },
)
async def upload_tender_documents(
    tender_id: UUID,
    request: Request,
    uow_factory: UowFactoryDependency,
    file_storage: FileStorageDependency,
    settings: SettingsDependency,
) -> TenderDocumentListResponseSchema:
    uploaded_by_user_id, uploads = await parse_document_upload(
        request,
        maximum_file_size_bytes=settings.max_document_size_bytes,
        maximum_files=settings.max_documents_per_upload,
    )
    result = UploadTenderDocument(
        uow_factory,
        file_storage,
        maximum_size_bytes=settings.max_document_size_bytes,
        maximum_files_per_upload=settings.max_documents_per_upload,
    ).execute(
        tender_id,
        UploadTenderDocumentRequest(
            uploaded_by_user_id=uploaded_by_user_id,
            files=uploads,
        ),
    )
    return _list_response(result)


@router.get(
    "/tenders/{tender_id}/documents",
    response_model=TenderDocumentListResponseSchema,
    summary="List active tender documents",
    responses={404: ERROR_RESPONSES[404]},
)
def list_tender_documents(
    tender_id: UUID,
    uow_factory: UowFactoryDependency,
) -> TenderDocumentListResponseSchema:
    return _list_response(ListTenderDocuments(uow_factory).execute(tender_id))


@router.get(
    "/documents/{document_id}",
    response_model=TenderDocumentResponseSchema,
    summary="Get document metadata",
    responses={404: ERROR_RESPONSES[404]},
)
def get_tender_document(
    document_id: UUID,
    uow_factory: UowFactoryDependency,
) -> TenderDocumentResponseSchema:
    result = GetTenderDocument(uow_factory).execute(document_id)
    return TenderDocumentResponseSchema.model_validate(result)


@router.get(
    "/documents/{document_id}/download",
    summary="Download a private PDF document",
    responses={404: ERROR_RESPONSES[404], 503: ERROR_RESPONSES[503]},
)
def download_tender_document(
    document_id: UUID,
    uow_factory: UowFactoryDependency,
    file_storage: FileStorageDependency,
) -> Response:
    result = DownloadTenderDocument(uow_factory, file_storage).execute(document_id)
    encoded_name = quote(result.original_file_name, safe="")
    return Response(
        content=result.content,
        media_type=result.mime_type,
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"document.pdf\"; filename*=UTF-8''{encoded_name}"
            ),
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete(
    "/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Logically delete a document",
    responses=ERROR_RESPONSES,
)
def delete_tender_document(
    document_id: UUID,
    deleted_by_user_id: Annotated[UUID, Query(description="User responsible for deletion")],
    uow_factory: UowFactoryDependency,
) -> Response:
    DeleteTenderDocument(uow_factory).execute(document_id, deleted_by_user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
