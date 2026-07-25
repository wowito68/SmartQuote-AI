from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.domain.tenders.entities import Tender
from app.domain.tenders.value_objects import TenderStatus


@dataclass(frozen=True, slots=True)
class CreateTenderRequest:
    title: str
    created_by_user_id: UUID
    description: str | None = None
    deadline: datetime | None = None


@dataclass(frozen=True, slots=True)
class UpdateTenderRequest:
    title: str
    description: str | None
    deadline: datetime | None
    status: TenderStatus


@dataclass(frozen=True, slots=True)
class TenderResponse:
    id: UUID
    title: str
    description: str | None
    status: TenderStatus
    deadline: datetime | None
    created_by_user_id: UUID
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_entity(cls, tender: Tender) -> "TenderResponse":
        return cls(
            id=tender.id,
            title=tender.title,
            description=tender.description,
            status=tender.status,
            deadline=tender.deadline,
            created_by_user_id=tender.created_by_user_id,
            created_at=tender.created_at,
            updated_at=tender.updated_at,
        )


@dataclass(frozen=True, slots=True)
class TenderListResponse:
    items: tuple[TenderResponse, ...]
    total: int
