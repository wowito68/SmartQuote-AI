from abc import ABC, abstractmethod
from collections.abc import Callable
from types import TracebackType

from app.application.ports.audit_event_repository import AuditEventRepository
from app.application.ports.catalog_repository import CatalogRepository
from app.application.ports.document_repository import TenderDocumentRepository
from app.application.ports.extraction_repository import ExtractionRepository
from app.application.ports.quote_analysis_artifact_repository import (
    QuoteAnalysisArtifactRepository,
)
from app.application.ports.quote_repository import QuoteRepository
from app.application.ports.rfq_repository import RfqRepository
from app.application.ports.supplier_repository import SupplierRepository
from app.application.ports.tender_repository import TenderRepository
from app.application.ports.user_lookup import UserLookup


class UnitOfWork(ABC):
    tenders: TenderRepository
    documents: TenderDocumentRepository
    extractions: ExtractionRepository
    audit_events: AuditEventRepository
    catalogs: CatalogRepository
    suppliers: SupplierRepository
    rfqs: RfqRepository
    quotes: QuoteRepository
    quote_artifacts: QuoteAnalysisArtifactRepository
    users: UserLookup

    @abstractmethod
    def __enter__(self) -> "UnitOfWork":
        raise NotImplementedError

    @abstractmethod
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def commit(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def rollback(self) -> None:
        raise NotImplementedError


UnitOfWorkFactory = Callable[[], UnitOfWork]
