from dataclasses import dataclass
from hashlib import sha256

from app.application.dtos.document import UploadDocumentFile
from app.domain.documents.entities import PDF_MIME_TYPE, normalize_original_file_name
from app.domain.documents.exceptions import (
    DocumentTooLarge,
    InvalidDocumentFile,
    TooManyDocuments,
)
from app.domain.documents.value_objects import FileHash

PDF_HEADER = b"%PDF-"
PDF_HEADER_SEARCH_LIMIT = 1024


@dataclass(frozen=True, slots=True)
class ValidatedDocumentFile:
    original_file_name: str
    content: bytes
    file_hash: FileHash

    @property
    def file_size(self) -> int:
        return len(self.content)


class DocumentFileValidator:
    def __init__(self, *, maximum_size_bytes: int, maximum_files_per_upload: int) -> None:
        if maximum_size_bytes <= 0 or maximum_files_per_upload <= 0:
            raise ValueError("Document upload limits must be greater than zero.")
        self._maximum_size_bytes = maximum_size_bytes
        self._maximum_files_per_upload = maximum_files_per_upload

    def validate_many(
        self,
        files: tuple[UploadDocumentFile, ...],
    ) -> tuple[ValidatedDocumentFile, ...]:
        if not files:
            raise InvalidDocumentFile("At least one PDF file is required.")
        if len(files) > self._maximum_files_per_upload:
            raise TooManyDocuments(
                f"A maximum of {self._maximum_files_per_upload} documents can be uploaded at once."
            )
        return tuple(self.validate(file) for file in files)

    def validate(self, file: UploadDocumentFile) -> ValidatedDocumentFile:
        original_file_name = normalize_original_file_name(file.original_file_name)
        declared_mime_type = (
            (file.declared_mime_type or "").split(";", maxsplit=1)[0].strip().lower()
        )
        if declared_mime_type != PDF_MIME_TYPE:
            raise InvalidDocumentFile("The declared MIME type must be application/pdf.")
        if not file.content:
            raise InvalidDocumentFile("Empty PDF files are not accepted.")
        if len(file.content) > self._maximum_size_bytes:
            raise DocumentTooLarge(
                f"Document exceeds the configured maximum of {self._maximum_size_bytes} bytes."
            )
        if PDF_HEADER not in file.content[:PDF_HEADER_SEARCH_LIMIT]:
            raise InvalidDocumentFile("The file content does not contain a valid PDF signature.")
        return ValidatedDocumentFile(
            original_file_name=original_file_name,
            content=file.content,
            file_hash=FileHash(sha256(file.content).hexdigest()),
        )
