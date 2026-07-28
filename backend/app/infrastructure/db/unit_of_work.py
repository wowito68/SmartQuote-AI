from types import TracebackType

from sqlalchemy.orm import Session, sessionmaker

from app.application.ports.unit_of_work import UnitOfWork
from app.infrastructure.db.repositories.audit_event_repository import (
    SqlAlchemyAuditEventRepository,
)
from app.infrastructure.db.repositories.catalog_repository import SqlAlchemyCatalogRepository
from app.infrastructure.db.repositories.document_processing_repository import (
    SqlAlchemyExtractionRepository,
)
from app.infrastructure.db.repositories.document_repository import (
    SqlAlchemyTenderDocumentRepository,
)
from app.infrastructure.db.repositories.rfq_repository import SqlAlchemyRfqRepository
from app.infrastructure.db.repositories.supplier_repository import (
    SqlAlchemySupplierRepository,
)
from app.infrastructure.db.repositories.tender_repository import SqlAlchemyTenderRepository
from app.infrastructure.db.repositories.user_lookup import SqlAlchemyUserLookup
from app.infrastructure.db.session import SessionLocal


class SqlAlchemyUnitOfWork(UnitOfWork):
    def __init__(self, session_factory: sessionmaker[Session] = SessionLocal) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None

    def __enter__(self) -> "SqlAlchemyUnitOfWork":
        self._session = self._session_factory()
        self.tenders = SqlAlchemyTenderRepository(self._session)
        self.documents = SqlAlchemyTenderDocumentRepository(self._session)
        self.extractions = SqlAlchemyExtractionRepository(self._session)
        self.audit_events = SqlAlchemyAuditEventRepository(self._session)
        self.catalogs = SqlAlchemyCatalogRepository(self._session)
        self.suppliers = SqlAlchemySupplierRepository(self._session)
        self.rfqs = SqlAlchemyRfqRepository(self._session)
        self.users = SqlAlchemyUserLookup(self._session)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._session is None:
            return
        if exc_type is not None:
            self.rollback()
        self._session.close()
        self._session = None

    def commit(self) -> None:
        if self._session is None:
            raise RuntimeError("Unit of Work is not active.")
        self._session.commit()

    def rollback(self) -> None:
        if self._session is not None:
            self._session.rollback()
