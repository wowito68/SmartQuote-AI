from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class TenderCreated:
    tender_id: UUID
    title: str
    event_id: UUID = field(default_factory=uuid4)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def event_type(self) -> str:
        return type(self).__name__

    def payload(self) -> dict[str, Any]:
        return {"title": self.title}


@dataclass(frozen=True, slots=True)
class TenderUpdated:
    tender_id: UUID
    changed_fields: tuple[str, ...]
    event_id: UUID = field(default_factory=uuid4)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def event_type(self) -> str:
        return type(self).__name__

    def payload(self) -> dict[str, Any]:
        return {"changed_fields": list(self.changed_fields)}


@dataclass(frozen=True, slots=True)
class TenderArchived:
    tender_id: UUID
    event_id: UUID = field(default_factory=uuid4)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def event_type(self) -> str:
        return type(self).__name__

    def payload(self) -> dict[str, Any]:
        return {}


TenderEvent = TenderCreated | TenderUpdated | TenderArchived
