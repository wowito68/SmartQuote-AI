from abc import ABC, abstractmethod
from uuid import UUID


class UserLookup(ABC):
    @abstractmethod
    def exists(self, user_id: UUID) -> bool:
        raise NotImplementedError
