import logging
from decimal import Decimal
from uuid import UUID

from celery import Task

from app.application.services.extraction_strategy import (
    ExtractionPolicy,
    FallbackDocumentTextExtractor,
)
from app.application.use_cases.quotes import ProcessSupplierQuote
from app.config.settings import get_settings
from app.domain.quotes.exceptions import QuoteExtractionFailure
from app.infrastructure.ai.openai_extraction_service import (
    OpenAIExtractionService,
    OpenAIResponsesHTTPClient,
)
from app.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork
from app.infrastructure.extraction.pdfplumber_extractor import PdfPlumberExtractor
from app.infrastructure.extraction.pymupdf_extractor import PyMuPDFExtractor
from app.infrastructure.prompts.file_prompt_registry import FilePromptRegistry
from app.infrastructure.storage.local_file_storage import LocalFileStorage
from app.infrastructure.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    base=Task,
    name="smartquote.quotes.analyze",
    autoretry_for=(QuoteExtractionFailure,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def analyze_supplier_quote(self: Task, quote_id: str) -> str:
    settings = get_settings()
    if settings.openai_api_key is None:
        raise QuoteExtractionFailure("SMARTQUOTE_OPENAI_API_KEY is not configured.")
    correlation_id = None
    if getattr(self.request, "headers", None):
        correlation_id = self.request.headers.get("correlation_id")
    logger.info(
        "quote_analysis_started",
        extra={"quote_id": quote_id, "correlation_id": correlation_id},
    )
    extractor = FallbackDocumentTextExtractor(
        PyMuPDFExtractor(),
        PdfPlumberExtractor(),
        ExtractionPolicy(
            minimum_characters=settings.extraction_minimum_characters,
            maximum_empty_page_percentage=settings.extraction_maximum_empty_page_percentage,
            minimum_characters_per_page=settings.extraction_minimum_characters_per_page,
        ),
    )
    client = OpenAIResponsesHTTPClient(
        api_key=settings.openai_api_key.get_secret_value(),
        base_url=settings.openai_base_url,
        timeout_seconds=settings.openai_timeout_seconds,
    )
    service = OpenAIExtractionService(
        client,
        input_cost_per_million_tokens=Decimal(str(settings.ai_input_cost_per_million_tokens)),
        output_cost_per_million_tokens=Decimal(str(settings.ai_output_cost_per_million_tokens)),
    )
    result = ProcessSupplierQuote(
        SqlAlchemyUnitOfWork,
        LocalFileStorage(settings.storage_root),
        extractor,
        service,
        FilePromptRegistry(),
        prompt_version=settings.quote_ai_prompt_version,
        model=settings.ai_model,
        temperature=settings.ai_temperature,
    ).execute(UUID(quote_id))
    logger.info(
        "quote_analysis_completed",
        extra={"quote_id": quote_id, "correlation_id": correlation_id},
    )
    return str(result)
