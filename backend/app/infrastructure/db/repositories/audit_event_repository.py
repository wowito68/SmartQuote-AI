from sqlalchemy.orm import Session

from app.application.ports.audit_event_repository import AuditEventRepository
from app.domain.tenders.events import TenderEvent
from app.infrastructure.db.models.audit_event import AuditEventModel


class SqlAlchemyAuditEventRepository(AuditEventRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def append(self, event: TenderEvent) -> None:
        self._session.add(
            AuditEventModel(
                id=event.event_id,
                aggregate_type="tender",
                aggregate_id=event.tender_id,
                event_type=event.event_type,
                payload=event.payload(),
                occurred_at=event.occurred_at,
            )
        )
