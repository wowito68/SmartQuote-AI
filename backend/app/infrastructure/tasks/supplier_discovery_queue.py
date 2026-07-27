from uuid import UUID

from app.application.ports.supplier_discovery_queue import SupplierDiscoveryQueue
from app.domain.suppliers.exceptions import SupplierDiscoveryQueueFailure
from app.infrastructure.tasks.celery_app import celery_app


class CelerySupplierDiscoveryQueue(SupplierDiscoveryQueue):
    def enqueue(self, run_id: UUID) -> None:
        try:
            celery_app.send_task(
                "smartquote.suppliers.discover",
                args=[str(run_id)],
                queue="supplier-discovery",
            )
        except Exception as exc:
            raise SupplierDiscoveryQueueFailure(str(exc)) from exc
