from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.tenders.entities import Tender
from app.infrastructure.db.models.audit_event import AuditEventModel
from app.infrastructure.db.models.user import UserModel
from app.infrastructure.db.repositories.tender_repository import (
    SqlAlchemyTenderRepository,
)


def persist_user(session: Session) -> UUID:
    user_id = uuid4()
    now = datetime.now(UTC)
    session.add(
        UserModel(
            id=user_id,
            email=f"{user_id}@example.com",
            full_name="Buyer",
            role="buyer",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
    )
    session.flush()
    return user_id


def test_repository_create_update_list_and_soft_delete(db_session: Session) -> None:
    creator = persist_user(db_session)
    repository = SqlAlchemyTenderRepository(db_session)
    created = repository.create(
        Tender(title="Hospital supplies", created_by_user_id=creator)
    )
    db_session.commit()

    found = repository.get_by_id(created.id)
    assert found is not None
    found.update_details(title="Updated hospital supplies")
    assert repository.update(found).title == "Updated hospital supplies"
    assert [item.id for item in repository.list()] == [created.id]
    assert repository.delete(created.id) is True
    db_session.commit()
    assert repository.get_by_id(created.id) is None
    assert repository.get_by_id(created.id, include_archived=True) is not None


def test_audit_model_is_persistable(db_session: Session) -> None:
    event = AuditEventModel(
        id=uuid4(),
        aggregate_type="tender",
        aggregate_id=uuid4(),
        event_type="TenderCreated",
        payload={},
        occurred_at=datetime.now(UTC),
    )
    db_session.add(event)
    db_session.commit()
    statement = select(AuditEventModel).where(AuditEventModel.id == event.id)
    assert db_session.scalar(statement) is not None
