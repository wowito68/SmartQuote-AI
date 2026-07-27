from abc import ABC, abstractmethod
from uuid import UUID


class SupplierDiscoveryQueue(ABC):
    @abstractmethod
    def enqueue(self, run_id: UUID) -> None: ...
