from abc import ABC, abstractmethod
from uuid import UUID

from app.domain.tenders.entities import Tender


class TenderRepository(ABC):
    @abstractmethod
    def create(self, tender: Tender) -> Tender:
        raise NotImplementedError

    @abstractmethod
    def get_by_id(self, tender_id: UUID) -> Tender | None:
        raise NotImplementedError

    @abstractmethod
    def list(self) -> list[Tender]:
        raise NotImplementedError

    @abstractmethod
    def update(self, tender: Tender) -> Tender:
        raise NotImplementedError

    @abstractmethod
    def delete(self, tender_id: UUID) -> bool:
        raise NotImplementedError

