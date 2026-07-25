from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.domain.shared.exceptions import InvalidStateTransitionError, ValidationError
from app.domain.shared.value_objects import EmailAddress, FileHash
from app.domain.tenders.entities import Tender, TenderDocument
from app.domain.tenders.exceptions import TenderAlreadyArchived
from app.domain.tenders.value_objects import DocumentStatus
from app.domain.users.entities import User


def make_document(tender_id=None) -> TenderDocument:
    return TenderDocument(
        tender_id=tender_id or uuid4(),
        file_name="  bases.PDF  ",
        file_path="  storage/bases.pdf  ",
        mime_type=" Application/PDF ",
        file_size=100,
        file_hash=FileHash("a" * 64),
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


def test_document_normalizes_and_changes_state() -> None:
    document = make_document()
    assert document.file_name == "bases.PDF"
    assert document.mime_type == "application/pdf"
    document.mark_valid()
    assert document.processing_status is DocumentStatus.VALID
    with pytest.raises(InvalidStateTransitionError):
        document.mark_valid()
    document.mark_rejected()
    assert document.processing_status is DocumentStatus.REJECTED


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("file_name", " "),
        ("file_path", " "),
        ("mime_type", " "),
        ("document_type", " "),
        ("file_size", 0),
    ],
)
def test_document_rejects_invalid_fields(field: str, value: object) -> None:
    kwargs = {
        "tender_id": uuid4(),
        "file_name": "bases.pdf",
        "file_path": "storage/bases.pdf",
        "mime_type": "application/pdf",
        "file_size": 100,
        "file_hash": FileHash("b" * 64),
        "uploaded_by_user_id": uuid4(),
        "document_type": "tender_pdf",
    }
    kwargs[field] = value
    with pytest.raises(ValidationError):
        TenderDocument(**kwargs)


def test_tender_add_document_and_compatibility_update() -> None:
    tender = Tender(title="Tender", created_by_user_id=uuid4())
    document = make_document(tender.id)
    tender.add_document(document)
    assert tender.documents == [document]
    tender.update_details(
        title=" Updated ",
        description=" Description ",
        deadline=datetime.now(UTC) + timedelta(days=1),
    )
    assert tender.title == "Updated"
    assert tender.description == "Description"


def test_tender_rejects_foreign_document_and_archived_document_addition() -> None:
    tender = Tender(title="Tender", created_by_user_id=uuid4())
    with pytest.raises(ValidationError):
        tender.add_document(make_document())
    tender.archive()
    with pytest.raises(TenderAlreadyArchived):
        tender.add_document(make_document(tender.id))
