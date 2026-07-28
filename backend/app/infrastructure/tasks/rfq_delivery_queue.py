from uuid import UUID

from app.application.ports.rfq_delivery_queue import RfqDeliveryQueue
from app.infrastructure.tasks.celery_app import celery_app


class CeleryRfqDeliveryQueue(RfqDeliveryQueue):
    def enqueue(self, rfq_id: UUID) -> None:
        celery_app.send_task("smartquote.rfqs.send", args=[str(rfq_id)], queue="rfq-delivery")
