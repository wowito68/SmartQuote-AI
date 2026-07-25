from sqlalchemy.orm import Session

from app.application.ports.audit_event_repository import AuditEventRepository
from app.domain.shared.events import DomainEvent
from app.infrastructure.db.models.audit_event import AuditEventModel


class SqlAlchemyAuditEventRepository(AuditEventRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def append(self, event: DomainEvent) -> None:
        self._session.add(
            AuditEventModel(
                id=event.event_id,
                aggregate_type=event.aggregate_type,
                aggregate_id=event.aggregate_id,
                event_type=event.event_type,
                payload=event.payload(),
                occurred_at=event.occurred_at,
            )
        )
