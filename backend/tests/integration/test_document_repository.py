from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session

from app.domain.documents.entities import TenderDocument
from app.domain.documents.exceptions import DuplicateDocument
from app.domain.documents.value_objects import DocumentStatus, FileHash
from app.domain.tenders.entities import Tender
from app.infrastructure.db.models.user import UserModel
from app.infrastructure.db.repositories.document_repository import (
    SqlAlchemyTenderDocumentRepository,
)
from app.infrastructure.db.repositories.tender_repository import SqlAlchemyTenderRepository


def persist_user(session: Session) -> UUID:
    user_id = uuid4()
    now = datetime.now(UTC)
    session.add(
        UserModel(
            id=user_id,
            email=f"{user_id}@example.com",
            full_name="Document User",
            role="buyer",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
    )
    session.flush()
    return user_id


def test_document_repository_create_find_list_update_and_soft_delete(db_session: Session) -> None:
    user_id = persist_user(db_session)
    tender = SqlAlchemyTenderRepository(db_session).create(
        Tender(title="Document tender", created_by_user_id=user_id)
    )
    repository = SqlAlchemyTenderDocumentRepository(db_session)
    document_id = uuid4()
    document = TenderDocument(
        id=document_id,
        tender_id=tender.id,
        original_file_name="bases.pdf",
        storage_key=f"tenders/{tender.id}/{document_id}.pdf",
        mime_type="application/pdf",
        file_size=128,
        file_hash=FileHash("d" * 64),
        uploaded_by_user_id=user_id,
    )

    created = repository.create(document)
    db_session.commit()
    assert repository.get_by_id(created.id) is not None
    assert repository.find_by_hash(tender.id, created.file_hash) is not None
    assert [item.id for item in repository.list_by_tender(tender.id)] == [created.id]

    created.mark_deleted()
    updated = repository.update(created)
    db_session.commit()
    assert updated.status is DocumentStatus.DELETED
    assert repository.get_by_id(created.id) is None
    assert repository.get_by_id(created.id, include_deleted=True) is not None
    assert repository.list_by_tender(tender.id) == []


def test_document_repository_translates_unique_hash_constraint(db_session: Session) -> None:
    user_id = persist_user(db_session)
    tender = SqlAlchemyTenderRepository(db_session).create(
        Tender(title="Concurrent duplicate tender", created_by_user_id=user_id)
    )
    repository = SqlAlchemyTenderDocumentRepository(db_session)
    shared_hash = FileHash("a" * 64)

    first_id = uuid4()
    repository.create(
        TenderDocument(
            id=first_id,
            tender_id=tender.id,
            original_file_name="first.pdf",
            storage_key=f"tenders/{tender.id}/{first_id}.pdf",
            mime_type="application/pdf",
            file_size=128,
            file_hash=shared_hash,
            uploaded_by_user_id=user_id,
        )
    )
    db_session.commit()

    second_id = uuid4()
    with pytest.raises(DuplicateDocument, match="same document"):
        repository.create(
            TenderDocument(
                id=second_id,
                tender_id=tender.id,
                original_file_name="second.pdf",
                storage_key=f"tenders/{tender.id}/{second_id}.pdf",
                mime_type="application/pdf",
                file_size=128,
                file_hash=shared_hash,
                uploaded_by_user_id=user_id,
            )
        )
    db_session.rollback()

    assert repository.find_by_hash(tender.id, shared_hash).id == first_id
