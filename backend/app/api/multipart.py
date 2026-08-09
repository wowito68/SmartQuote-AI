from email.parser import BytesParser
from email.policy import default
from uuid import UUID

from fastapi import Request

from app.application.dtos.document import UploadDocumentFile
from app.domain.documents.exceptions import DocumentTooLarge, InvalidDocumentFile

MULTIPART_OVERHEAD_ALLOWANCE = 1024 * 1024


async def parse_multipart_upload(
    request: Request,
    *,
    maximum_file_size_bytes: int,
    maximum_files: int,
    allowed_text_fields: set[str],
) -> tuple[dict[str, str], tuple[UploadDocumentFile, ...]]:
    content_type = request.headers.get("content-type", "")
    if not content_type.lower().startswith("multipart/form-data"):
        raise InvalidDocumentFile("Content-Type must be multipart/form-data.")

    maximum_body_size = maximum_file_size_bytes * maximum_files + MULTIPART_OVERHEAD_ALLOWANCE
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > maximum_body_size:
            raise DocumentTooLarge("Multipart upload exceeds the configured request limit.")

    envelope = f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode() + bytes(body)
    message = BytesParser(policy=default).parsebytes(envelope)
    if not message.is_multipart():
        raise InvalidDocumentFile("Malformed multipart/form-data request.")

    fields: dict[str, str] = {}
    files: list[UploadDocumentFile] = []
    for part in message.iter_parts():
        field_name = part.get_param("name", header="content-disposition")
        if field_name in allowed_text_fields:
            payload = part.get_payload(decode=True) or b""
            charset = part.get_content_charset() or "utf-8"
            fields[str(field_name)] = payload.decode(charset).strip()
        elif field_name == "files":
            if len(files) >= maximum_files:
                raise InvalidDocumentFile("Too many files were provided in the upload.")
            files.append(
                UploadDocumentFile(
                    original_file_name=part.get_filename() or "",
                    declared_mime_type=part.get_content_type(),
                    content=part.get_payload(decode=True) or b"",
                )
            )
    return fields, tuple(files)


async def parse_document_upload(
    request: Request,
    *,
    maximum_file_size_bytes: int,
    maximum_files: int,
) -> tuple[UUID, tuple[UploadDocumentFile, ...]]:
    fields, files = await parse_multipart_upload(
        request,
        maximum_file_size_bytes=maximum_file_size_bytes,
        maximum_files=maximum_files,
        allowed_text_fields={"uploaded_by_user_id"},
    )
    uploader_value = fields.get("uploaded_by_user_id")
    if uploader_value is None:
        raise InvalidDocumentFile("uploaded_by_user_id is required.")
    try:
        uploader_id = UUID(uploader_value)
    except ValueError as exc:
        raise InvalidDocumentFile("uploaded_by_user_id must be a valid UUID.") from exc
    return uploader_id, files


async def parse_quote_upload(
    request: Request,
    *,
    maximum_file_size_bytes: int,
) -> tuple[UUID, UUID, UUID | None, tuple[UploadDocumentFile, ...]]:
    fields, files = await parse_multipart_upload(
        request,
        maximum_file_size_bytes=maximum_file_size_bytes,
        maximum_files=1,
        allowed_text_fields={"uploaded_by_user_id", "supplier_id", "rfq_request_id"},
    )
    try:
        uploader = UUID(fields["uploaded_by_user_id"])
        supplier = UUID(fields["supplier_id"])
        rfq = UUID(fields["rfq_request_id"]) if fields.get("rfq_request_id") else None
    except KeyError as exc:
        raise InvalidDocumentFile(f"{exc.args[0]} is required.") from exc
    except ValueError as exc:
        raise InvalidDocumentFile("Quote upload UUID fields are invalid.") from exc
    return uploader, supplier, rfq, files
