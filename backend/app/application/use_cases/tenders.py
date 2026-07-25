from uuid import UUID

from app.application.dtos.tender import (
    CreateTenderRequest,
    TenderListResponse,
    TenderResponse,
    UpdateTenderRequest,
)
from app.application.exceptions import TenderCreatorNotFound, TenderNotFound
from app.application.ports.unit_of_work import UnitOfWorkFactory
from app.domain.tenders.entities import Tender
from app.domain.tenders.events import TenderArchived, TenderCreated, TenderUpdated


class CreateTender:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, request: CreateTenderRequest) -> TenderResponse:
        tender = Tender(
            title=request.title,
            description=request.description,
            deadline=request.deadline,
            created_by_user_id=request.created_by_user_id,
        )
        with self._uow_factory() as uow:
            if not uow.users.exists(request.created_by_user_id):
                raise TenderCreatorNotFound("Tender creator does not exist.")
            created = uow.tenders.create(tender)
            uow.audit_events.append(TenderCreated(tender_id=created.id, title=created.title))
            uow.commit()
        return TenderResponse.from_entity(created)


class GetTender:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, tender_id: UUID) -> TenderResponse:
        with self._uow_factory() as uow:
            tender = uow.tenders.get_by_id(tender_id)
            if tender is None:
                raise TenderNotFound("Tender was not found.")
        return TenderResponse.from_entity(tender)


class ListTenders:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self) -> TenderListResponse:
        with self._uow_factory() as uow:
            tenders = uow.tenders.list()
        items = tuple(TenderResponse.from_entity(tender) for tender in tenders)
        return TenderListResponse(items=items, total=len(items))


class UpdateTender:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, tender_id: UUID, request: UpdateTenderRequest) -> TenderResponse:
        with self._uow_factory() as uow:
            tender = uow.tenders.get_by_id(tender_id, include_archived=True)
            if tender is None:
                raise TenderNotFound("Tender was not found.")
            changed_fields = tender.replace_details(
                title=request.title,
                description=request.description,
                deadline=request.deadline,
                status=request.status,
            )
            updated = uow.tenders.update(tender)
            if changed_fields:
                uow.audit_events.append(
                    TenderUpdated(tender_id=updated.id, changed_fields=changed_fields)
                )
            uow.commit()
        return TenderResponse.from_entity(updated)


class ArchiveTender:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, tender_id: UUID) -> None:
        with self._uow_factory() as uow:
            tender = uow.tenders.get_by_id(tender_id, include_archived=True)
            if tender is None:
                raise TenderNotFound("Tender was not found.")
            tender.archive()
            uow.tenders.update(tender)
            uow.audit_events.append(TenderArchived(tender_id=tender.id))
            uow.commit()
