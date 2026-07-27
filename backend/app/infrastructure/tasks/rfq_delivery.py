from uuid import UUID

from celery import Task

from app.application.use_cases.rfqs import DeliverRfq
from app.config.settings import get_settings
from app.domain.rfqs.exceptions import EmailDeliveryError
from app.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork
from app.infrastructure.email.smtp_email_sender import SMTPEmailSender
from app.infrastructure.email.stored_document_attachment_provider import (
    StoredDocumentAttachmentProvider,
)
from app.infrastructure.storage.local_file_storage import LocalFileStorage
from app.infrastructure.tasks.celery_app import celery_app


def get_attachment_provider() -> StoredDocumentAttachmentProvider:
    settings = get_settings()
    return StoredDocumentAttachmentProvider(
        SqlAlchemyUnitOfWork,
        LocalFileStorage(settings.storage_root),
        settings.max_email_attachment_bytes,
    )


def get_email_sender() -> SMTPEmailSender:
    settings = get_settings()
    return SMTPEmailSender(
        host=settings.smtp_host,
        port=settings.smtp_port,
        sender_email=settings.smtp_sender_email,
        sender_name=settings.smtp_sender_name,
        username=settings.smtp_username,
        password=settings.smtp_password.get_secret_value() if settings.smtp_password else None,
        use_tls=settings.smtp_use_tls,
        use_ssl=settings.smtp_use_ssl,
        timeout_seconds=settings.smtp_timeout_seconds,
        message_id_domain=settings.smtp_message_id_domain,
    )


@celery_app.task(
    bind=True,
    base=Task,
    name="smartquote.rfqs.send",
    autoretry_for=(EmailDeliveryError,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def send_rfq_email(self: Task, rfq_id: str) -> str:
    message_id = DeliverRfq(
        SqlAlchemyUnitOfWork,
        get_attachment_provider(),
        get_email_sender(),
    ).execute(UUID(rfq_id))
    return str(message_id)
