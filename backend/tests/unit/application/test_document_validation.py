from hashlib import sha256

import pytest

from app.application.dtos.document import UploadDocumentFile
from app.application.services.document_validation import DocumentFileValidator
from app.domain.documents.exceptions import (
    DocumentTooLarge,
    InvalidDocumentFile,
    TooManyDocuments,
)

PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n"


def validator(*, size: int = 1024, count: int = 2) -> DocumentFileValidator:
    return DocumentFileValidator(maximum_size_bytes=size, maximum_files_per_upload=count)


def upload(name: str = "bases.pdf", mime: str = "application/pdf", content: bytes = PDF):
    return UploadDocumentFile(name, mime, content)


def test_validator_calculates_sha256_and_accepts_header_with_prefix() -> None:
    content = b"\xef\xbb\xbf" + PDF
    result = validator().validate(upload(content=content))
    assert result.file_hash.value == sha256(content).hexdigest()
    assert result.file_size == len(content)
    assert result.original_file_name == "bases.pdf"


@pytest.mark.parametrize(
    "candidate",
    [
        upload(name="../bases.pdf"),
        upload(name="bases.txt"),
        upload(mime="text/plain"),
        upload(content=b"not a pdf"),
        upload(content=b""),
    ],
)
def test_validator_rejects_invalid_pdf_inputs(candidate: UploadDocumentFile) -> None:
    with pytest.raises(InvalidDocumentFile):
        validator().validate(candidate)


def test_validator_enforces_size_and_file_count() -> None:
    with pytest.raises(DocumentTooLarge):
        validator(size=5).validate(upload())
    with pytest.raises(TooManyDocuments):
        validator(count=1).validate_many((upload(), upload(name="other.pdf")))
    with pytest.raises(InvalidDocumentFile):
        validator().validate_many(())
