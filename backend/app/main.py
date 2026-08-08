from fastapi import FastAPI

from app.api.error_handlers import register_exception_handlers
from app.api.routes.catalog import router as catalog_router
from app.api.routes.documents import router as documents_router
from app.api.routes.health import router as health_router
from app.api.routes.quotes import router as quotes_router
from app.api.routes.rfqs import router as rfqs_router
from app.api.routes.suppliers import router as suppliers_router
from app.api.routes.tenders import router as tenders_router
from app.config.settings import get_settings
from app.infrastructure.observability.logging import configure_logging


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()
    application = FastAPI(
        title=settings.project_name,
        version=settings.version,
        description="REST API for SmartQuote AI tender sourcing, RFQ delivery and quote comparison.",
    )
    register_exception_handlers(application)
    application.include_router(health_router)
    application.include_router(quotes_router, prefix=settings.api_v1_prefix)
    application.include_router(rfqs_router, prefix=settings.api_v1_prefix)
    application.include_router(suppliers_router, prefix=settings.api_v1_prefix)
    application.include_router(catalog_router, prefix=settings.api_v1_prefix)
    application.include_router(documents_router, prefix=settings.api_v1_prefix)
    application.include_router(tenders_router, prefix=settings.api_v1_prefix)
    return application


app = create_app()
