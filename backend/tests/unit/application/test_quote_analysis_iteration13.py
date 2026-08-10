import urllib.error
from uuid import uuid4

import pytest

from app.application.use_cases.quote_analysis import _provider_error_is_retryable
from app.domain.catalog.exceptions import AIExtractionFailure, AIResponseValidationError
from app.domain.quotes.analysis import (
    mark_analyzed,
    mark_pending_review,
    mark_ready_for_analysis,
    restart_analysis,
    start_analysis,
)
from app.domain.quotes.artifacts import ExtractionArtifact
from app.domain.quotes.entities import Quote
from app.domain.quotes.exceptions import InvalidQuoteState
from app.domain.quotes.value_objects import QuoteStatus


def _quote() -> Quote:
    return Quote(
        tender_id=uuid4(),
        tender_supplier_id=uuid4(),
        supplier_id=uuid4(),
        original_file_name="supplier.pdf",
        storage_key="private/supplier.pdf",
        mime_type="application/pdf",
        file_size=100,
        file_hash="a" * 64,
        uploaded_by_user_id=uuid4(),
    )


def test_iteration13_analysis_state_machine_is_explicit_and_requires_review() -> None:
    quote = _quote()
    quote.start_validation()
    mark_ready_for_analysis(quote)
    assert quote.status is QuoteStatus.READY_FOR_ANALYSIS

    start_analysis(quote)
    assert quote.status is QuoteStatus.ANALYZING
    mark_analyzed(quote)
    assert quote.status is QuoteStatus.ANALYZED
    mark_pending_review(quote)
    assert quote.status is QuoteStatus.PENDING_REVIEW

    restart_analysis(quote)
    assert quote.status is QuoteStatus.READY_FOR_ANALYSIS


def test_analysis_cannot_start_from_received_without_validation_helper() -> None:
    quote = _quote()
    with pytest.raises(InvalidQuoteState):
        start_analysis(quote)


def test_extraction_artifact_keeps_structured_output_immutable_from_caller() -> None:
    payload = {"summary": {"currency": "MXN"}, "items": []}
    artifact = ExtractionArtifact(
        extraction_run_id=uuid4(),
        schema_version="2.0.0",
        structured_output=payload,
    )
    payload["items"] = [{"product_name": "mutated later"}]
    assert artifact.structured_output["items"] == []


def test_provider_retry_classification_is_transient_only() -> None:
    transient_http = AIExtractionFailure("provider unavailable")
    transient_http.__cause__ = urllib.error.HTTPError(
        "https://example.invalid",
        429,
        "rate limited",
        hdrs=None,
        fp=None,
    )
    permanent_http = AIExtractionFailure("bad request")
    permanent_http.__cause__ = urllib.error.HTTPError(
        "https://example.invalid",
        400,
        "bad request",
        hdrs=None,
        fp=None,
    )
    invalid_schema = AIResponseValidationError("invalid structured output")

    assert _provider_error_is_retryable(transient_http) is True
    assert _provider_error_is_retryable(permanent_http) is False
    assert _provider_error_is_retryable(invalid_schema) is False
