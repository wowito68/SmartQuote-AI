from uuid import UUID

from app.application.ports.quote_analysis_queue import QuoteAnalysisQueue
from app.infrastructure.tasks.celery_app import celery_app


class CeleryQuoteAnalysisQueue(QuoteAnalysisQueue):
    def enqueue(
        self,
        quote_id: UUID,
        correlation_id: str | None = None,
        *,
        task_record_id: UUID | None = None,
        force_reprocess: bool = False,
    ) -> None:
        headers = {"correlation_id": correlation_id} if correlation_id else None
        celery_app.send_task(
            "smartquote.quotes.analyze",
            args=[str(quote_id)],
            kwargs={
                "task_record_id": str(task_record_id) if task_record_id else None,
                "force_reprocess": force_reprocess,
            },
            queue="quote-analysis",
            headers=headers,
        )
