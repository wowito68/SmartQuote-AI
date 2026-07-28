from celery import Celery

from app.config.settings import get_settings

settings = get_settings()

celery_app = Celery(
    "smartquote",
    broker=settings.celery_broker_url.get_secret_value(),
    backend=settings.celery_result_backend.get_secret_value(),
    include=[
        "app.infrastructure.tasks.document_pipeline",
        "app.infrastructure.tasks.catalog_extraction",
        "app.infrastructure.tasks.supplier_discovery",
        "app.infrastructure.tasks.rfq_delivery",
    ],
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,
    task_routes={
        "smartquote.documents.*": {"queue": "document-processing"},
        "smartquote.catalog.*": {"queue": "ai-extraction"},
        "smartquote.suppliers.*": {"queue": "supplier-discovery"},
        "smartquote.rfqs.*": {"queue": "rfq-delivery"},
    },
    task_always_eager=settings.celery_task_always_eager,
    task_eager_propagates=True,
    broker_transport_options={"visibility_timeout": 3600},
    beat_schedule={
        "detect-pending-documents": {
            "task": "smartquote.documents.detect_pending",
            "schedule": settings.pending_document_scan_seconds,
        }
    },
)
