import logging
from decimal import Decimal
from uuid import UUID

from celery import Task

from app.application.services.extraction_strategy import FallbackDocumentTextExtractor
from app.application.use_cases.quotes import ProcessSupplierQuote
from app.config.settings import get_settings
from app.domain.quotes.exceptions import RetryableQuoteExtractionFailure
from app.domain.quotes.value_objects import QuoteStatus
from app.infrastructure.ai.openai_extraction_service import (
    OpenAIExtractionService,
    OpenAIResponsesHTTPClient,
)
from app.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork
from app.infrastructure.extraction.pdfplumber_text_extractor import PdfPlumberTextExtractor
from app.infrastructure.extraction.pymupdf_text_extractor import PyMuPDFTextExtractor
from app.infrastructure.prompts.file_prompt_registry import FilePromptRegistry
from app.infrastructure.storage.local_file_storage import LocalFileStorage
from app.infrastructure.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def get_text_extractor() -> FallbackDocumentTextExtractor:
    return FallbackDocumentTextExtractor(PyMuPDFTextExtractor(), PdfPlumberTextExtractor())


def get_ai_service() -> OpenAIExtractionService:
    settings = get_settings()
    if settings.openai_api_key is None or not settings.openai_api_key.get_secret_value():
        raise RetryableQuoteExtractionFailure("OpenAI API key is not configured for quote extraction.")
    client = OpenAIResponsesHTTPClient(
        api_key=settings.openai_api_key.get_secret_value(),
        base_url=settings.openai_base_url,
        timeout_seconds=settings.openai_timeout_seconds,
    )
    return OpenAIExtractionService(
        client,
        input_cost_per_million_tokens=Decimal(str(settings.ai_input_cost_per_million_tokens)),
        output_cost_per_million_tokens=Decimal(str(settings.ai_output_cost_per_million_tokens)),
    )


@celery_app.task(
    bind=True,
    base=Task,
    name="smartquote.quotes.analyze",
    autoretry_for=(RetryableQuoteExtractionFailure,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def analyze_quote(
    self: Task,
    quote_id: str,
    task_record_id: str | None = None,
    force_reprocess: bool = False,
) -> str:
    settings = get_settings()
    correlation_id = None
    headers = getattr(self.request, "headers", None) or {}
    if isinstance(headers, dict):
        correlation_id = headers.get("correlation_id")
    if getattr(self.request, "retries", 0):
        with SqlAlchemyUnitOfWork() as uow:
            quote = uow.quotes.get_quote(UUID(quote_id), for_update=True)
            if quote is not None and quote.status is QuoteStatus.FAILED:
                quote.restart_processing()
                uow.quotes.update_quote(quote)
                uow.commit()
    logger.info(
        "quote_analysis_task_started",
        extra={
            "quote_id": quote_id,
            "task_record_id": task_record_id,
            "correlation_id": correlation_id,
            "celery_task_id": getattr(self.request, "id", None),
            "celery_retries": getattr(self.request, "retries", 0),
            "force_reprocess": force_reprocess,
        },
    )
    processor = ProcessSupplierQuote(
        SqlAlchemyUnitOfWork,
        LocalFileStorage(settings.storage_root),
        get_text_extractor(),
        get_ai_service(),
        FilePromptRegistry(),
        prompt_version=settings.quote_ai_prompt_version,
        model=settings.ai_model,
        temperature=settings.ai_temperature,
        confidence_low_threshold=settings.quote_confidence_medium_threshold,
    )
    processor.execute(
        UUID(quote_id),
        UUID(task_record_id) if task_record_id else None,
        force_reprocess=force_reprocess,
    )
    return quote_id
