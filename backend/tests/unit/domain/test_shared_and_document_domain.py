from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.domain.documents.entities import TenderDocument
from app.domain.documents.exceptions import (
    DocumentAlreadyDeleted,
    DuplicateDocument,
    InvalidDocumentFile,
)
from app.domain.documents.value_objects import DocumentStatus
from app.domain.shared.exceptions import ValidationError
from app.domain.shared.value_objects import EmailAddress, FileHash
from app.domain.tenders.entities import Tender
from app.domain.tenders.exceptions import InvalidTenderState, TenderAlreadyArchived
from app.domain.tenders.value_objects import TenderStatus
from app.domain.users.entities import User


def make_document(tender_id=None, *, digest: str = "a" * 64) -> TenderDocument:
    document_id = uuid4()
    return TenderDocument(
        id=document_id,
        tender_id=tender_id or uuid4(),
        original_file_name="  bases.PDF  ",
        storage_key=f"tenders/{tender_id or uuid4()}/{document_id}.pdf",
        mime_type=" Application/PDF ",
        file_size=100,
        file_hash=FileHash(digest),
        uploaded_by_user_id=uuid4(),
    )


def test_shared_value_objects_normalize_and_validate() -> None:
    assert str(EmailAddress(" Buyer@Example.com ")) == "buyer@example.com"
    assert str(FileHash("A" * 64)) == "a" * 64
    with pytest.raises(ValidationError):
        EmailAddress("invalid")
    with pytest.raises(ValidationError):
        FileHash("abc")


def test_user_entity_validates_and_normalizes() -> None:
    user = User(email=EmailAddress("buyer@example.com"), full_name=" Buyer ", role=" buyer ")
    assert user.full_name == "Buyer"
    assert user.role == "buyer"
    with pytest.raises(ValidationError):
        User(email=EmailAddress("buyer@example.com"), full_name=" ")
    with pytest.raises(ValidationError):
        User(email=EmailAddress("buyer@example.com"), full_name="Buyer", role=" ")


def test_document_normalizes_and_soft_deletes() -> None:
    document = make_document()
    assert document.original_file_name == "bases.PDF"
    assert document.mime_type == "application/pdf"
    assert document.status is DocumentStatus.UPLOADED

    document.mark_deleted()
    assert document.status is DocumentStatus.DELETED
    assert document.deleted_at is not None
    with pytest.raises(DocumentAlreadyDeleted):
        document.mark_deleted()


def test_document_can_be_rejected_before_deletion() -> None:
    document = make_document()
    document.mark_rejected()
    assert document.status is DocumentStatus.REJECTED


@pytest.mark.parametrize(
    ("field", "value", "exception"),
    [
        ("original_file_name", " ", ValidationError),
        ("original_file_name", "../bases.pdf", InvalidDocumentFile),
        ("original_file_name", "bases.txt", InvalidDocumentFile),
        ("storage_key", "../storage/bases.pdf", ValidationError),
        ("mime_type", "text/plain", InvalidDocumentFile),
        ("file_size", 0, ValidationError),
    ],
)
def test_document_rejects_invalid_fields(
    field: str,
    value: object,
    exception: type[Exception],
) -> None:
    document_id = uuid4()
    kwargs = {
        "id": document_id,
        "tender_id": uuid4(),
        "original_file_name": "bases.pdf",
        "storage_key": f"tenders/{uuid4()}/{document_id}.pdf",
        "mime_type": "application/pdf",
        "file_size": 100,
        "file_hash": FileHash("b" * 64),
        "uploaded_by_user_id": uuid4(),
    }
    kwargs[field] = value
    with pytest.raises(exception):
        TenderDocument(**kwargs)


def test_tender_add_document_updates_status_and_rejects_duplicate() -> None:
    tender = Tender(title="Tender", created_by_user_id=uuid4())
    document = make_document(tender.id)
    tender.add_document(document)
    assert tender.documents == [document]
    assert tender.status is TenderStatus.DOCUMENTS_PENDING

    with pytest.raises(DuplicateDocument):
        tender.add_document(make_document(tender.id, digest=document.file_hash.value))

    tender.update_details(
        title=" Updated ",
        description=" Description ",
        deadline=datetime.now(UTC) + timedelta(days=1),
    )
    assert tender.title == "Updated"
    assert tender.description == "Description"


def test_tender_rejects_foreign_archived_and_closed_document_uploads() -> None:
    tender = Tender(title="Tender", created_by_user_id=uuid4())
    with pytest.raises(ValidationError):
        tender.add_document(make_document())

    tender.archive()
    with pytest.raises(TenderAlreadyArchived):
        tender.add_document(make_document(tender.id))

    closed = Tender(
        title="Closed",
        created_by_user_id=uuid4(),
        status=TenderStatus.CLOSED,
    )
    with pytest.raises(InvalidTenderState):
        closed.ensure_accepts_documents()
