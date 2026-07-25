from abc import ABC, abstractmethod

from app.domain.shared.events import DomainEvent


class AuditEventRepository(ABC):
    @abstractmethod
    def append(self, event: DomainEvent) -> None:
        raise NotImplementedError
