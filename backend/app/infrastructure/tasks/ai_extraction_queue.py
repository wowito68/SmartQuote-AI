from uuid import UUID

from app.application.ports.ai_extraction_queue import AIExtractionQueue
from app.infrastructure.tasks.celery_app import celery_app


class CeleryAIExtractionQueue(AIExtractionQueue):
    def enqueue(self, run_id: UUID) -> None:
        celery_app.send_task(
            "smartquote.catalog.extract",
            args=[str(run_id)],
            queue="ai-extraction",
        )
