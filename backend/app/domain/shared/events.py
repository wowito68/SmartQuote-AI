from datetime import datetime
from typing import Any, Protocol
from uuid import UUID


class DomainEvent(Protocol):
    event_id: UUID
    occurred_at: datetime

    @property
    def aggregate_type(self) -> str: ...

    @property
    def aggregate_id(self) -> UUID: ...

    @property
    def event_type(self) -> str: ...

    def payload(self) -> dict[str, Any]: ...
