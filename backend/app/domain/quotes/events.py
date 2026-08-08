from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class QuoteEvent:
    aggregate_id_value: UUID
    event_name: str
    data: dict[str, Any] = field(default_factory=dict)
    aggregate_type: str = "quote"
    event_id: UUID = field(default_factory=uuid4)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def aggregate_id(self) -> UUID:
        return self.aggregate_id_value

    @property
    def event_type(self) -> str:
        return self.event_name

    def payload(self) -> dict[str, Any]:
        return self.data


def quote_event(
    aggregate_id: UUID,
    event_name: str,
    *,
    aggregate_type: str = "quote",
    **data: Any,
) -> QuoteEvent:
    return QuoteEvent(aggregate_id, event_name, data, aggregate_type)
