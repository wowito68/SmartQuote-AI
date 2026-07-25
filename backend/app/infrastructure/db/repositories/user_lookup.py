from uuid import UUID

from sqlalchemy.orm import Session

from app.application.ports.user_lookup import UserLookup
from app.infrastructure.db.models.user import UserModel


class SqlAlchemyUserLookup(UserLookup):
    def __init__(self, session: Session) -> None:
        self._session = session

    def exists(self, user_id: UUID) -> bool:
        return self._session.get(UserModel, user_id) is not None
