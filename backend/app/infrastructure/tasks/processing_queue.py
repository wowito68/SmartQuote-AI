from uuid import UUID

from app.application.ports.document_processing_queue import DocumentProcessingQueue
from app.domain.documents.exceptions import DocumentProcessingQueueFailure
from app.infrastructure.tasks.celery_app import celery_app


class CeleryDocumentProcessingQueue(DocumentProcessingQueue):
    def enqueue(self, document_id: UUID) -> None:
        try:
            celery_app.send_task(
                "smartquote.documents.start_pipeline",
                args=[str(document_id)],
                queue="document-processing",
            )
        except Exception as error:
            raise DocumentProcessingQueueFailure(
                "Document could not be published to Redis."
            ) from error
