from fastapi import FastAPI

from app.api.routes.health import router as health_router
from app.config.settings import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title=settings.project_name,
        version=settings.version,
    )
    application.include_router(health_router)
    return application


app = create_app()

