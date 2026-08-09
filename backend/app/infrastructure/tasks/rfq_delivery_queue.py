from uuid import UUID

from app.application.ports.rfq_delivery_queue import RfqDeliveryQueue
from app.infrastructure.tasks.celery_app import celery_app


class CeleryRfqDeliveryQueue(RfqDeliveryQueue):
    def enqueue(
        self,
        rfq_id: UUID,
        *,
        task_record_id: UUID | None = None,
        correlation_id: str | None = None,
    ) -> None:
        args = [str(rfq_id)]
        if task_record_id is not None:
            args.append(str(task_record_id))
            args.append(correlation_id or str(task_record_id))
        celery_app.send_task("smartquote.rfqs.send", args=args, queue="rfq-delivery")
