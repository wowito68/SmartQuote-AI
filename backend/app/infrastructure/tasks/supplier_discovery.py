from uuid import UUID

from celery import Task

from app.application.services.supplier_deduplication import SupplierDeduplicationService
from app.application.services.supplier_matching import SupplierMatchingService
from app.application.services.supplier_normalization import SupplierCandidateNormalizer
from app.application.services.supplier_query_builder import SupplierQueryBuilder
from app.application.use_cases.supplier_discovery_v2 import (
    CompleteSupplierDiscoveryV2,
    DeduplicateSuppliersV2,
    DiscoverSupplierContactsV2,
    DiscoverSuppliersV2,
    MatchSuppliersV2,
    NormalizeSupplierCandidates,
    ProcessSupplierDiscoveryRunV2,
)
from app.config.settings import get_settings
from app.domain.suppliers.exceptions import SupplierSearchFailure
from app.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork
from app.infrastructure.search.inline_contact_discovery import InlineContactDiscoveryService
from app.infrastructure.search.search_provider_adapter import (
    JsonDirectorySearchClient,
    SearchProviderAdapter,
)
from app.infrastructure.tasks.celery_app import celery_app


def get_supplier_search_service() -> SearchProviderAdapter:
    settings = get_settings()
    return SearchProviderAdapter(JsonDirectorySearchClient(settings.supplier_directory_path))


def _query_builder() -> SupplierQueryBuilder:
    return SupplierQueryBuilder(get_settings().supplier_search_query_version)


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
    settings = get_settings()
    result = ProcessSupplierDiscoveryRunV2(
        SqlAlchemyUnitOfWork,
        get_supplier_search_service(),
        _query_builder(),
        SupplierCandidateNormalizer(),
        SupplierDeduplicationService(),
        InlineContactDiscoveryService(),
        SupplierMatchingService(settings.supplier_matching_algorithm_version),
    ).execute(UUID(run_id))
    return str(result)


@celery_app.task(name="smartquote.suppliers.search")
def search_suppliers(run_id: str) -> str:
    return str(
        DiscoverSuppliersV2(
            SqlAlchemyUnitOfWork,
            get_supplier_search_service(),
            _query_builder(),
        ).execute(UUID(run_id))
    )


@celery_app.task(name="smartquote.suppliers.normalize")
def normalize_supplier_candidates(run_id: str) -> str:
    return str(
        NormalizeSupplierCandidates(
            SqlAlchemyUnitOfWork,
            SupplierCandidateNormalizer(),
        ).execute(UUID(run_id))
    )


@celery_app.task(name="smartquote.suppliers.deduplicate")
def deduplicate_suppliers(run_id: str) -> str:
    return str(
        DeduplicateSuppliersV2(
            SqlAlchemyUnitOfWork,
            SupplierDeduplicationService(),
        ).execute(UUID(run_id))
    )


@celery_app.task(name="smartquote.suppliers.discover_contacts")
def discover_supplier_contacts(run_id: str) -> str:
    return str(
        DiscoverSupplierContactsV2(
            SqlAlchemyUnitOfWork,
            InlineContactDiscoveryService(),
        ).execute(UUID(run_id))
    )


@celery_app.task(name="smartquote.suppliers.match")
def match_suppliers(run_id: str) -> str:
    return str(
        MatchSuppliersV2(
            SqlAlchemyUnitOfWork,
            SupplierMatchingService(get_settings().supplier_matching_algorithm_version),
        ).execute(UUID(run_id))
    )


@celery_app.task(name="smartquote.suppliers.start_review")
def start_supplier_review(run_id: str) -> str:
    return str(CompleteSupplierDiscoveryV2(SqlAlchemyUnitOfWork).execute(UUID(run_id)))
