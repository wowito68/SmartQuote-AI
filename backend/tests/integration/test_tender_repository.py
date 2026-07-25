from uuid import uuid4

from app.domain.shared.value_objects import EmailAddress, FileHash
from app.domain.tenders.entities import Tender, TenderDocument
from app.domain.tenders.value_objects import TenderStatus
from app.domain.users.entities import User
from app.infrastructure.db.models.user import UserModel
from app.infrastructure.db.repositories.tender_repository import SqlAlchemyTenderRepository
from sqlalchemy.orm import Session


def persist_user(session: Session) -> User:
    user = User(email=EmailAddress("buyer@example.com"), full_name="Buyer User")
    session.add(
        UserModel(
            id=user.id,
            email=user.email.value,
            full_name=user.full_name,
            role=user.role,
            is_active=user.is_active,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )
    )
    session.flush()
    return user


def test_tender_repository_create_get_list_update_and_soft_delete(db_session: Session) -> None:
    user = persist_user(db_session)
    repository = SqlAlchemyTenderRepository(db_session)
    tender = Tender(title="Hospital supplies", created_by_user_id=user.id)
    document = TenderDocument(
        tender_id=tender.id,
        file_name="bases.pdf",
        file_path="storage/bases.pdf",
        mime_type="application/pdf",
        file_size=2048,
        file_hash=FileHash("d" * 64),
        uploaded_by_user_id=user.id,
    )
    tender.add_document(document)

    created = repository.create(tender)
    db_session.commit()

    found = repository.get_by_id(created.id)
    assert found is not None
    assert found.title == "Hospital supplies"
    assert found.status is TenderStatus.DOCUMENTS_PENDING
    assert len(found.documents) == 1

    found.update_details(title="Updated hospital supplies")
    updated = repository.update(found)
    db_session.commit()
    assert updated.title == "Updated hospital supplies"

    listed = repository.list()
    assert [item.id for item in listed] == [created.id]

    assert repository.delete(created.id) is True
    db_session.commit()

    assert repository.get_by_id(created.id) is None
    assert repository.list() == []


def test_tender_repository_delete_returns_false_for_missing_tender(db_session: Session) -> None:
    repository = SqlAlchemyTenderRepository(db_session)

    assert repository.delete(uuid4()) is False

