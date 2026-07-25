from email.parser import BytesParser
from email.policy import default
from uuid import UUID

from fastapi import Request

from app.application.dtos.document import UploadDocumentFile
from app.domain.documents.exceptions import DocumentTooLarge, InvalidDocumentFile

MULTIPART_OVERHEAD_ALLOWANCE = 1024 * 1024


async def parse_document_upload(
    request: Request,
    *,
    maximum_file_size_bytes: int,
    maximum_files: int,
) -> tuple[UUID, tuple[UploadDocumentFile, ...]]:
    content_type = request.headers.get("content-type", "")
    if not content_type.lower().startswith("multipart/form-data"):
        raise InvalidDocumentFile("Content-Type must be multipart/form-data.")

    maximum_body_size = maximum_file_size_bytes * maximum_files + MULTIPART_OVERHEAD_ALLOWANCE
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > maximum_body_size:
            raise DocumentTooLarge("Multipart upload exceeds the configured request limit.")

    envelope = (
        f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8")
        + bytes(body)
    )
    message = BytesParser(policy=default).parsebytes(envelope)
    if not message.is_multipart():
        raise InvalidDocumentFile("Malformed multipart/form-data request.")

    uploader_value: str | None = None
    files: list[UploadDocumentFile] = []
    for part in message.iter_parts():
        field_name = part.get_param("name", header="content-disposition")
        if field_name == "uploaded_by_user_id":
            payload = part.get_payload(decode=True) or b""
            charset = part.get_content_charset() or "utf-8"
            uploader_value = payload.decode(charset).strip()
        elif field_name == "files":
            files.append(
                UploadDocumentFile(
                    original_file_name=part.get_filename() or "",
                    declared_mime_type=part.get_content_type(),
                    content=part.get_payload(decode=True) or b"",
                )
            )

    if uploader_value is None:
        raise InvalidDocumentFile("uploaded_by_user_id is required.")
    try:
        uploader_id = UUID(uploader_value)
    except ValueError as exc:
        raise InvalidDocumentFile("uploaded_by_user_id must be a valid UUID.") from exc
    return uploader_id, tuple(files)
