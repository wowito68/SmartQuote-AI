from functools import lru_cache

from app.application.ports.ai_extraction_queue import AIExtractionQueue
from app.application.ports.document_processing_queue import DocumentProcessingQueue
from app.application.ports.file_storage import FileStorage
from app.application.ports.prompt_registry import PromptRegistry
from app.application.ports.supplier_discovery_queue import SupplierDiscoveryQueue
from app.application.ports.supplier_search_service import SupplierSearchService
from app.application.ports.unit_of_work import UnitOfWorkFactory
from app.config.settings import get_settings
from app.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork
from app.infrastructure.prompts.file_prompt_registry import FilePromptRegistry
from app.infrastructure.search.search_provider_adapter import (
    JsonDirectorySearchClient,
    SearchProviderAdapter,
)
from app.infrastructure.storage.local_file_storage import LocalFileStorage
from app.infrastructure.tasks.ai_extraction_queue import CeleryAIExtractionQueue
from app.infrastructure.tasks.processing_queue import CeleryDocumentProcessingQueue
from app.infrastructure.tasks.supplier_discovery_queue import (
    CelerySupplierDiscoveryQueue,
)


def get_uow_factory() -> UnitOfWorkFactory:
    return SqlAlchemyUnitOfWork


@lru_cache
def get_file_storage() -> FileStorage:
    return LocalFileStorage(get_settings().storage_root)


@lru_cache
def get_processing_queue() -> DocumentProcessingQueue:
    return CeleryDocumentProcessingQueue()


@lru_cache
def get_ai_extraction_queue() -> AIExtractionQueue:
    return CeleryAIExtractionQueue()


@lru_cache
def get_prompt_registry() -> PromptRegistry:
    return FilePromptRegistry()


@lru_cache
def get_supplier_discovery_queue() -> SupplierDiscoveryQueue:
    return CelerySupplierDiscoveryQueue()


@lru_cache
def get_supplier_search_service() -> SupplierSearchService:
    settings = get_settings()
    return SearchProviderAdapter(JsonDirectorySearchClient(settings.supplier_directory_path))
