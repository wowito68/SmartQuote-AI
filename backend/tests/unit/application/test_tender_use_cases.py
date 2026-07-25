from copy import deepcopy
from types import TracebackType
from uuid import UUID, uuid4

import pytest

from app.application.dtos.tender import CreateTenderRequest, UpdateTenderRequest
from app.application.exceptions import TenderCreatorNotFound, TenderNotFound
from app.application.ports.unit_of_work import UnitOfWork
from app.application.use_cases.tenders import (
    ArchiveTender,
    CreateTender,
    GetTender,
    ListTenders,
    UpdateTender,
)
from app.domain.tenders.entities import Tender
from app.domain.tenders.events import TenderArchived, TenderCreated, TenderUpdated
from app.domain.tenders.exceptions import TenderAlreadyArchived
from app.domain.tenders.value_objects import TenderStatus


class FakeTenderRepository:
    def __init__(self, storage: dict[UUID, Tender]) -> None:
        self.storage = storage

    def create(self, tender: Tender) -> Tender:
        self.storage[tender.id] = deepcopy(tender)
        return deepcopy(tender)

    def get_by_id(
        self,
        tender_id: UUID,
        *,
        include_archived: bool = False,
    ) -> Tender | None:
        tender = self.storage.get(tender_id)
        if tender is None or (tender.is_deleted and not include_archived):
            return None
        return deepcopy(tender)

    def list(self) -> list[Tender]:
        return [deepcopy(tender) for tender in self.storage.values() if not tender.is_deleted]

    def update(self, tender: Tender) -> Tender:
        self.storage[tender.id] = deepcopy(tender)
        return deepcopy(tender)

    def delete(self, tender_id: UUID) -> bool:
        return False


class FakeAuditRepository:
    def __init__(self, events: list[object]) -> None:
        self.events = events

    def append(self, event: object) -> None:
        self.events.append(event)


class FakeUserLookup:
    def __init__(self, users: set[UUID]) -> None:
        self.users = users

    def exists(self, user_id: UUID) -> bool:
        return user_id in self.users


class FakeUnitOfWork(UnitOfWork):
    def __init__(
        self,
        storage: dict[UUID, Tender],
        events: list[object],
        users: set[UUID],
    ) -> None:
        self.tenders = FakeTenderRepository(storage)
        self.audit_events = FakeAuditRepository(events)
        self.users = FakeUserLookup(users)
        self.committed = False

    def __enter__(self) -> "FakeUnitOfWork":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        return None


@pytest.fixture()
def context():
    storage: dict[UUID, Tender] = {}
    events: list[object] = []
    creator = uuid4()
    users = {creator}

    def factory() -> FakeUnitOfWork:
        return FakeUnitOfWork(storage, events, users)

    return storage, events, creator, factory


def test_complete_tender_use_case_flow(context) -> None:
    storage, events, creator, factory = context
    created = CreateTender(factory).execute(
        CreateTenderRequest(title="Tender A", created_by_user_id=creator)
    )
    assert created.id in storage
    assert isinstance(events[-1], TenderCreated)
    assert GetTender(factory).execute(created.id).id == created.id
    assert ListTenders(factory).execute().total == 1

    updated = UpdateTender(factory).execute(
        created.id,
        UpdateTenderRequest(
            title="Tender B",
            description="Updated",
            deadline=None,
            status=TenderStatus.DOCUMENTS_PENDING,
        ),
    )
    assert updated.title == "Tender B"
    assert isinstance(events[-1], TenderUpdated)

    ArchiveTender(factory).execute(created.id)
    assert isinstance(events[-1], TenderArchived)
    assert ListTenders(factory).execute().total == 0
    with pytest.raises(TenderNotFound):
        GetTender(factory).execute(created.id)
    with pytest.raises(TenderAlreadyArchived):
        ArchiveTender(factory).execute(created.id)


def test_create_rejects_unknown_creator(context) -> None:
    _, _, _, factory = context
    with pytest.raises(TenderCreatorNotFound):
        CreateTender(factory).execute(
            CreateTenderRequest(title="Tender", created_by_user_id=uuid4())
        )
