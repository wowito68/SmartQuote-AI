from decimal import Decimal
from uuid import UUID

from celery import Task
from app.application.services.catalog_normalizer import CatalogNormalizer
from app.application.use_cases.catalog import ProcessAIExtractionRun
from app.config.settings import get_settings
from app.domain.catalog.exceptions import AIExtractionFailure
from app.infrastructure.ai.openai_extraction_service import (
    OpenAIExtractionService,
    OpenAIResponsesHTTPClient,
)
from app.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork
from app.infrastructure.prompts.file_prompt_registry import FilePromptRegistry
from app.infrastructure.tasks.celery_app import celery_app


@celery_app.task(
    bind=True,
    base=Task,
    name="smartquote.catalog.extract",
    autoretry_for=(AIExtractionFailure,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def extract_tender_catalog(self: Task, run_id: str) -> str:
    settings = get_settings()
    if settings.openai_api_key is None:
        raise AIExtractionFailure("SMARTQUOTE_OPENAI_API_KEY is not configured.")
    client = OpenAIResponsesHTTPClient(
        api_key=settings.openai_api_key.get_secret_value(),
        base_url=settings.openai_base_url,
        timeout_seconds=settings.openai_timeout_seconds,
    )
    service = OpenAIExtractionService(
        client,
        input_cost_per_million_tokens=Decimal(
            str(settings.ai_input_cost_per_million_tokens)
        ),
        output_cost_per_million_tokens=Decimal(
            str(settings.ai_output_cost_per_million_tokens)
        ),
    )
    result = ProcessAIExtractionRun(
        SqlAlchemyUnitOfWork,
        service,
        FilePromptRegistry(),
        CatalogNormalizer(),
    ).execute(UUID(run_id))
    return str(result)
