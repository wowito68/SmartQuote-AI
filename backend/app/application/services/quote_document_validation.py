from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import PurePath
from zipfile import BadZipFile, ZipFile

from app.application.dtos.document import UploadDocumentFile
from app.domain.documents.exceptions import DocumentTooLarge, InvalidDocumentFile
from app.domain.documents.value_objects import FileHash

PDF_MIME = "application/pdf"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
SUPPORTED_QUOTE_MIME_TYPES = frozenset({PDF_MIME, XLSX_MIME, DOCX_MIME})
_EXTENSION_BY_MIME = {PDF_MIME: ".pdf", XLSX_MIME: ".xlsx", DOCX_MIME: ".docx"}


@dataclass(frozen=True, slots=True)
class ValidatedQuoteFile:
    original_file_name: str
    content: bytes
    file_hash: FileHash
    mime_type: str

    @property
    def file_size(self) -> int:
        return len(self.content)


def _validate_ooxml(content: bytes, mime_type: str) -> None:
    try:
        with ZipFile(BytesIO(content)) as archive:
            names = set(archive.namelist())
    except (BadZipFile, OSError) as exc:
        raise InvalidDocumentFile("The uploaded Office file is not a valid OOXML package.") from exc
    required = (
        {"[Content_Types].xml", "xl/workbook.xml"}
        if mime_type == XLSX_MIME
        else {"[Content_Types].xml", "word/document.xml"}
    )
    if not required <= names:
        raise InvalidDocumentFile("The uploaded Office file does not match its declared type.")
    lower_names = {name.casefold() for name in names}
    if any(name.endswith("vbaproject.bin") for name in lower_names):
        raise InvalidDocumentFile("Macro-enabled Office documents are not accepted.")
    if mime_type == XLSX_MIME and any(name.startswith("xl/externallinks/") for name in lower_names):
        raise InvalidDocumentFile("XLSX external links are not accepted for quote processing.")


class QuoteDocumentValidator:
    def __init__(self, maximum_size_bytes: int) -> None:
        if maximum_size_bytes <= 0:
            raise ValueError("Quote upload size limit must be positive.")
        self._maximum_size_bytes = maximum_size_bytes

    def validate(self, file: UploadDocumentFile) -> ValidatedQuoteFile:
        name = PurePath(file.original_file_name).name.strip()
        if not name or name != file.original_file_name.strip() or len(name) > 255:
            raise InvalidDocumentFile("Quote file name is invalid.")
        mime = (file.declared_mime_type or "").split(";", 1)[0].strip().lower()
        if mime not in SUPPORTED_QUOTE_MIME_TYPES:
            raise InvalidDocumentFile("Quote must be PDF, XLSX or DOCX.")
        if PurePath(name).suffix.casefold() != _EXTENSION_BY_MIME[mime]:
            raise InvalidDocumentFile("Quote file extension does not match its MIME type.")
        if not file.content:
            raise InvalidDocumentFile("Empty quote files are not accepted.")
        if len(file.content) > self._maximum_size_bytes:
            raise DocumentTooLarge(
                f"Quote exceeds the configured maximum of {self._maximum_size_bytes} bytes."
            )
        if mime == PDF_MIME:
            if b"%PDF-" not in file.content[:1024]:
                raise InvalidDocumentFile("Quote content does not contain a valid PDF signature.")
        else:
            _validate_ooxml(file.content, mime)
        return ValidatedQuoteFile(
            original_file_name=name,
            content=file.content,
            file_hash=FileHash(sha256(file.content).hexdigest()),
            mime_type=mime,
        )
