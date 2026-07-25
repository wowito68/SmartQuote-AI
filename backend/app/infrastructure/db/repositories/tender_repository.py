from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.application.ports.tender_repository import TenderRepository
from app.domain.tenders.entities import Tender
from app.infrastructure.db.mappers.tender_mapper import (
    tender_to_domain,
    tender_to_model,
    update_tender_model,
)
from app.infrastructure.db.models.tender import TenderModel


class SqlAlchemyTenderRepository(TenderRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, tender: Tender) -> Tender:
        model = tender_to_model(tender)
        self._session.add(model)
        self._session.flush()
        return tender_to_domain(model)

    def get_by_id(self, tender_id: UUID, *, include_archived: bool = False) -> Tender | None:
        statement = (
            select(TenderModel)
            .options(selectinload(TenderModel.documents))
            .where(TenderModel.id == tender_id)
        )
        if not include_archived:
            statement = statement.where(TenderModel.deleted_at.is_(None))
        model = self._session.scalars(statement).first()
        return tender_to_domain(model) if model else None

    def list(self) -> list[Tender]:
        statement = (
            select(TenderModel)
            .options(selectinload(TenderModel.documents))
            .where(TenderModel.deleted_at.is_(None))
            .order_by(TenderModel.created_at.desc())
        )
        return [tender_to_domain(model) for model in self._session.scalars(statement)]

    def update(self, tender: Tender) -> Tender:
        statement = (
            select(TenderModel)
            .options(selectinload(TenderModel.documents))
            .where(TenderModel.id == tender.id)
        )
        model = self._session.scalars(statement).first()
        if model is None:
            raise ValueError("Tender does not exist.")
        update_tender_model(model, tender)
        self._session.flush()
        return tender_to_domain(model)

    def delete(self, tender_id: UUID) -> bool:
        tender = self.get_by_id(tender_id)
        if tender is None:
            return False
        tender.archive()
        self.update(tender)
        return True
