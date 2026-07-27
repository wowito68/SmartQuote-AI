from uuid import UUID

from celery import Task

from app.application.services.supplier_deduplication import SupplierDeduplicationService
from app.application.services.supplier_matching import SupplierMatchingService
from app.application.use_cases.supplier_discovery import (
    DeduplicateSuppliers,
    DiscoverSupplierContacts,
    DiscoverSuppliers,
    MatchSuppliers,
    ProcessSupplierDiscoveryRun,
    StartSupplierReview,
)
from app.config.settings import get_settings
from app.domain.suppliers.exceptions import SupplierSearchFailure
from app.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork
from app.infrastructure.search.search_provider_adapter import (
    JsonDirectorySearchClient,
    SearchProviderAdapter,
)
from app.infrastructure.tasks.celery_app import celery_app


def get_supplier_search_service() -> SearchProviderAdapter:
    settings = get_settings()
    return SearchProviderAdapter(JsonDirectorySearchClient(settings.supplier_directory_path))


@celery_app.task(
    bind=True,
    base=Task,
    name="smartquote.suppliers.discover",
    autoretry_for=(SupplierSearchFailure,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def discover_tender_suppliers(self: Task, run_id: str) -> str:
    result = ProcessSupplierDiscoveryRun(
        SqlAlchemyUnitOfWork,
        get_supplier_search_service(),
        SupplierDeduplicationService(),
        SupplierMatchingService(get_settings().supplier_matching_algorithm_version),
    ).execute(UUID(run_id))
    return str(result)


@celery_app.task(name="smartquote.suppliers.search")
def search_suppliers(run_id: str) -> str:
    return str(
        DiscoverSuppliers(
            SqlAlchemyUnitOfWork,
            get_supplier_search_service(),
        ).execute(UUID(run_id))
    )


@celery_app.task(name="smartquote.suppliers.deduplicate")
def deduplicate_suppliers(run_id: str) -> str:
    return str(
        DeduplicateSuppliers(
            SqlAlchemyUnitOfWork,
            SupplierDeduplicationService(),
        ).execute(UUID(run_id))
    )


@celery_app.task(name="smartquote.suppliers.discover_contacts")
def discover_supplier_contacts(run_id: str) -> str:
    return str(DiscoverSupplierContacts(SqlAlchemyUnitOfWork).execute(UUID(run_id)))


@celery_app.task(name="smartquote.suppliers.match")
def match_suppliers(run_id: str) -> str:
    return str(
        MatchSuppliers(
            SqlAlchemyUnitOfWork,
            SupplierMatchingService(get_settings().supplier_matching_algorithm_version),
        ).execute(UUID(run_id))
    )


@celery_app.task(name="smartquote.suppliers.start_review")
def start_supplier_review(run_id: str) -> str:
    return str(StartSupplierReview(SqlAlchemyUnitOfWork).execute(UUID(run_id)))
