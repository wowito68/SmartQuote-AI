from functools import lru_cache

from app.application.ports.ai_extraction_queue import AIExtractionQueue
from app.application.ports.attachment_provider import AttachmentProvider
from app.application.ports.email_composer import EmailComposer
from app.application.ports.email_sender import EmailSender
from app.application.ports.document_processing_queue import DocumentProcessingQueue
from app.application.ports.file_storage import FileStorage
from app.application.ports.prompt_registry import PromptRegistry
from app.application.ports.rfq_delivery_queue import RfqDeliveryQueue
from app.application.ports.supplier_discovery_queue import SupplierDiscoveryQueue
from app.application.ports.supplier_search_service import SupplierSearchService
from app.application.ports.unit_of_work import UnitOfWorkFactory
from app.config.settings import get_settings
from app.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork
from app.infrastructure.email.jinja_template_renderer import JinjaTemplateRenderer
from app.infrastructure.email.smtp_email_sender import SMTPEmailSender
from app.infrastructure.email.stored_document_attachment_provider import (
    StoredDocumentAttachmentProvider,
)
from app.infrastructure.email.template_email_composer import TemplateEmailComposer
from app.infrastructure.prompts.file_prompt_registry import FilePromptRegistry
from app.infrastructure.search.search_provider_adapter import (
    JsonDirectorySearchClient,
    SearchProviderAdapter,
)
from app.infrastructure.storage.local_file_storage import LocalFileStorage
from app.infrastructure.tasks.ai_extraction_queue import CeleryAIExtractionQueue
from app.infrastructure.tasks.processing_queue import CeleryDocumentProcessingQueue
from app.infrastructure.tasks.rfq_delivery_queue import CeleryRfqDeliveryQueue
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


@lru_cache
def get_email_composer() -> EmailComposer:
    return TemplateEmailComposer(JinjaTemplateRenderer())


@lru_cache
def get_attachment_provider() -> AttachmentProvider:
    settings = get_settings()
    return StoredDocumentAttachmentProvider(
        get_uow_factory(),
        get_file_storage(),
        settings.max_email_attachment_bytes,
    )


@lru_cache
def get_email_sender() -> EmailSender:
    settings = get_settings()
    return SMTPEmailSender(
        host=settings.smtp_host,
        port=settings.smtp_port,
        sender_email=settings.smtp_sender_email,
        sender_name=settings.smtp_sender_name,
        username=settings.smtp_username,
        password=(
            settings.smtp_password.get_secret_value() if settings.smtp_password else None
        ),
        use_tls=settings.smtp_use_tls,
        use_ssl=settings.smtp_use_ssl,
        timeout_seconds=settings.smtp_timeout_seconds,
        message_id_domain=settings.smtp_message_id_domain,
    )


@lru_cache
def get_rfq_delivery_queue() -> RfqDeliveryQueue:
    return CeleryRfqDeliveryQueue()
