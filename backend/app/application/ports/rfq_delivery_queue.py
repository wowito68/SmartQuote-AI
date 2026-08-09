from abc import ABC, abstractmethod
from uuid import UUID


class RfqDeliveryQueue(ABC):
    @abstractmethod
    def enqueue(
        self,
        rfq_id: UUID,
        *,
        task_record_id: UUID | None = None,
        correlation_id: str | None = None,
    ) -> None: ...
