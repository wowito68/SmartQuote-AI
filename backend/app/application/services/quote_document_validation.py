from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import PurePath
from zipfile import BadZipFile, ZipFile

from app.application.dtos.document import UploadDocumentFile
from app.domain.documents.exceptions import DocumentTooLarge, InvalidDocumentFile
from app.domain.quotes.value_objects import QuoteDocumentType


@dataclass(frozen=True, slots=True)
class ValidatedQuoteFile:
    original_file_name: str
    content: bytes
    file_hash: str
    mime_type: str
    document_type: QuoteDocumentType

    @property
    def file_size(self) -> int:
        return len(self.content)


class QuoteDocumentValidator:
    PDF_MIME = "application/pdf"
    XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ZIP_MIMES = {"application/zip", "application/octet-stream"}

    def __init__(self, maximum_size_bytes: int) -> None:
        if maximum_size_bytes <= 0:
            raise ValueError("Quote document maximum size must be positive.")
        self._maximum_size_bytes = maximum_size_bytes

    @staticmethod
    def _safe_name(value: str) -> str:
        name = value.strip()
        if not name or len(name) > 255:
            raise InvalidDocumentFile("Quote file name is invalid.")
        if PurePath(name).name != name or "/" in name or "\\" in name:
            raise InvalidDocumentFile("Quote file name must not contain a path.")
        if any(ord(character) < 32 for character in name):
            raise InvalidDocumentFile("Quote file name contains control characters.")
        return name

    @staticmethod
    def _zip_entries(content: bytes) -> set[str]:
        try:
            with ZipFile(BytesIO(content)) as archive:
                return set(archive.namelist())
        except BadZipFile as exc:
            raise InvalidDocumentFile("Office quote file is not a valid ZIP container.") from exc

    def validate(self, file: UploadDocumentFile) -> ValidatedQuoteFile:
        name = self._safe_name(file.original_file_name)
        if not file.content:
            raise InvalidDocumentFile("Empty quote files are not accepted.")
        if len(file.content) > self._maximum_size_bytes:
            raise DocumentTooLarge(
                f"Quote document exceeds the configured maximum of {self._maximum_size_bytes} bytes."
            )
        extension = name.rsplit(".", 1)[-1].casefold() if "." in name else ""
        declared = (file.declared_mime_type or "").split(";", 1)[0].strip().lower()
        if extension in {"xlsm", "docm", "xls", "doc"}:
            raise InvalidDocumentFile("Macro-enabled or legacy Office quote files are not supported.")
        if extension == "pdf":
            if b"%PDF-" not in file.content[:1024]:
                raise InvalidDocumentFile("Quote PDF signature is invalid.")
            if declared and declared != self.PDF_MIME:
                raise InvalidDocumentFile("Declared MIME type does not match PDF content.")
            document_type = QuoteDocumentType.PDF
            mime = self.PDF_MIME
        elif extension in {"xlsx", "docx"}:
            if not file.content.startswith(b"PK"):
                raise InvalidDocumentFile("Office quote file signature is invalid.")
            entries = self._zip_entries(file.content)
            if "[Content_Types].xml" not in entries:
                raise InvalidDocumentFile("Office quote container is missing content types metadata.")
            if extension == "xlsx":
                if "xl/workbook.xml" not in entries:
                    raise InvalidDocumentFile("XLSX quote container is invalid.")
                if declared and declared not in {self.XLSX_MIME, *self.ZIP_MIMES}:
                    raise InvalidDocumentFile("Declared MIME type does not match XLSX content.")
                document_type = QuoteDocumentType.XLSX
                mime = self.XLSX_MIME
            else:
                if "word/document.xml" not in entries:
                    raise InvalidDocumentFile("DOCX quote container is invalid.")
                if declared and declared not in {self.DOCX_MIME, *self.ZIP_MIMES}:
                    raise InvalidDocumentFile("Declared MIME type does not match DOCX content.")
                document_type = QuoteDocumentType.DOCX
                mime = self.DOCX_MIME
        else:
            raise InvalidDocumentFile("Only PDF, XLSX and DOCX quote files are supported.")
        return ValidatedQuoteFile(
            original_file_name=name,
            content=file.content,
            file_hash=sha256(file.content).hexdigest(),
            mime_type=mime,
            document_type=document_type,
        )
