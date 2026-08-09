from uuid import UUID

from sqlalchemy.orm import Session

from app.application.ports.user_lookup import UserAuthorization, UserLookup
from app.infrastructure.db.models.user import UserModel


class SqlAlchemyUserLookup(UserLookup):
    def __init__(self, session: Session) -> None:
        self._session = session

    def exists(self, user_id: UUID) -> bool:
        return self._session.get(UserModel, user_id) is not None

    def get_authorization(self, user_id: UUID) -> UserAuthorization | None:
        model = self._session.get(UserModel, user_id)
        if model is None:
            return None
        return UserAuthorization(
            user_id=model.id,
            role=model.role,
            is_active=model.is_active,
        )
