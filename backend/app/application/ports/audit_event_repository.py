from abc import ABC, abstractmethod

from app.domain.tenders.events import TenderEvent


class AuditEventRepository(ABC):
    @abstractmethod
    def append(self, event: TenderEvent) -> None:
        raise NotImplementedError
