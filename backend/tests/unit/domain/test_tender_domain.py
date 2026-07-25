from uuid import uuid4

import pytest
from app.domain.shared.exceptions import InvalidStateTransitionError, ValidationError
from app.domain.shared.value_objects import EmailAddress, FileHash
from app.domain.tenders.entities import Tender, TenderDocument
from app.domain.tenders.value_objects import DocumentStatus, TenderStatus
from app.domain.users.entities import User


def test_user_requires_valid_email() -> None:
    with pytest.raises(ValidationError):
        User(email=EmailAddress("not-an-email"), full_name="Buyer")


def test_tender_requires_title() -> None:
    with pytest.raises(ValidationError):
        Tender(title=" ", created_by_user_id=uuid4())


def test_tender_document_requires_sha256_hash() -> None:
    with pytest.raises(ValidationError):
        FileHash("abc")


def test_adding_document_moves_tender_to_documents_pending() -> None:
    user_id = uuid4()
    tender = Tender(title="Medical equipment", created_by_user_id=user_id)
    document = TenderDocument(
        tender_id=tender.id,
        file_name="tender.pdf",
        file_path="storage/tender.pdf",
        mime_type="application/pdf",
        file_size=1024,
        file_hash=FileHash("a" * 64),
        uploaded_by_user_id=user_id,
    )

    tender.add_document(document)

    assert tender.status is TenderStatus.DOCUMENTS_PENDING
    assert tender.documents == [document]


def test_deleted_tender_cannot_receive_documents() -> None:
    user_id = uuid4()
    tender = Tender(title="Medical equipment", created_by_user_id=user_id)
    tender.soft_delete()
    document = TenderDocument(
        tender_id=tender.id,
        file_name="tender.pdf",
        file_path="storage/tender.pdf",
        mime_type="application/pdf",
        file_size=1024,
        file_hash=FileHash("b" * 64),
        uploaded_by_user_id=user_id,
    )

    with pytest.raises(InvalidStateTransitionError):
        tender.add_document(document)


def test_document_mark_valid_transition() -> None:
    user_id = uuid4()
    document = TenderDocument(
        tender_id=uuid4(),
        file_name="tender.pdf",
        file_path="storage/tender.pdf",
        mime_type="application/pdf",
        file_size=1024,
        file_hash=FileHash("c" * 64),
        uploaded_by_user_id=user_id,
    )

    document.mark_valid()

    assert document.processing_status is DocumentStatus.VALID

