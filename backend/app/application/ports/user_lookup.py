from abc import ABC, abstractmethod
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class UserAuthorization:
    user_id: UUID
    role: str
    is_active: bool


class UserLookup(ABC):
    @abstractmethod
    def exists(self, user_id: UUID) -> bool:
        raise NotImplementedError

    @abstractmethod
    def get_authorization(self, user_id: UUID) -> UserAuthorization | None:
        raise NotImplementedError
