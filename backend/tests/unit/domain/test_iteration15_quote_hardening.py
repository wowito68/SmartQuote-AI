from datetime import datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from app.domain.quotes.entities import Quote, QuoteDocument, QuoteExtractionRun, QuoteItem, QuoteTaskRecord
from app.domain.quotes.exceptions import InvalidQuoteState
from app.domain.quotes.value_objects import (
    ComplianceStatus,
    ProductMatchStatus,
    QuoteDocumentProcessingStatus,
    QuoteDocumentType,
    QuoteExtractionRunStatus,
    QuoteStatus,
    QuoteTaskStatus,
    QuoteWarning,
)
from app.domain.shared.exceptions import ValidationError


def _quote(**changes) -> Quote:
    values = {
        "tender_id": uuid4(),
        "tender_supplier_id": uuid4(),
        "supplier_id": uuid4(),
        "original_file_name": " quote.pdf ",
        "storage_key": "private/quote.pdf",
        "mime_type": "application/pdf",
        "file_size": 100,
        "file_hash": "a" * 64,
        "uploaded_by_user_id": uuid4(),
    }
    values.update(changes)
    return Quote(**values)


def _run(**changes) -> QuoteExtractionRun:
    values = {
        "quote_id": uuid4(),
        "tender_id": uuid4(),
        "supplier_id": uuid4(),
        "idempotency_key": "b" * 64,
        "extractor_version": "1",
        "prompt_version": "2",
        "model": "test-model",
        "schema_version": "2",
        "schema_hash": "c" * 64,
        "extractor_name": "parser",
    }
    values.update(changes)
    return QuoteExtractionRun(**values)


def test_quote_validates_metadata_and_normalizes_summary() -> None:
    for changes in (
        {"original_file_name": " "},
        {"file_size": 0},
        {"file_hash": "bad"},
        {"version": 0},
        {"currency": "peso"},
        {"delivery_time_days": -1},
        {"total_amount": Decimal("NaN")},
    ):
        with pytest.raises(ValidationError):
            _quote(**changes)

    quote = _quote(currency="mxn", valid_until=datetime(2030, 1, 1))
    assert quote.original_file_name == "quote.pdf"
    assert quote.currency == "MXN"
    assert quote.valid_until is not None and quote.valid_until.tzinfo is not None
    with pytest.raises(InvalidQuoteState):
        quote.apply_summary(
            currency="MXN",
            subtotal_amount=Decimal("1"),
            tax_amount=Decimal("0"),
            total_amount=Decimal("1"),
            delivery_time_days=1,
            commercial_terms=None,
            valid_until=None,
        )

    quote.start_validation()
    quote.start_validation()
    quote.start_extraction()
    quote.mark_extracted()
    quote.apply_summary(
        currency="mxn",
        subtotal_amount=Decimal("100"),
        tax_amount=Decimal("16"),
        total_amount=Decimal("116"),
        delivery_time_days=5,
        commercial_terms="  net   30  ",
        valid_until=datetime(2030, 1, 1),
    )
    assert quote.status is QuoteStatus.NORMALIZED
    assert quote.commercial_terms == "net 30"


def test_quote_review_failure_reprocess_and_immutability() -> None:
    quote = _quote()
    quote.start_validation()
    quote.start_extraction()
    quote.mark_extracted()
    quote.mark_normalized()
    quote.start_review()
    quote.record_manual_edit()
    assert quote.manual_edit_count == 1 and quote.version == 2
    with pytest.raises(ValidationError):
        quote.reject(uuid4(), " ")
    quote.reject(uuid4(), " incorrect pricing ")
    assert quote.status is QuoteStatus.REJECTED
    quote.restart_processing()
    quote.mark_failed(RuntimeError("provider down"))
    quote.mark_failed("still down")
    assert quote.last_error == "still down"
    quote.restart_processing()
    quote.start_extraction()
    quote.mark_extracted()
    quote.mark_normalized()
    quote.start_review()
    run_id = uuid4()
    quote.approve(uuid4(), run_id)
    assert quote.approved_extraction_run_id == run_id
    with pytest.raises(InvalidQuoteState):
        quote.record_manual_edit()
    with pytest.raises(InvalidQuoteState):
        quote.mark_failed("late")
    quote.include_in_comparison()
    with pytest.raises(InvalidQuoteState):
        quote.restart_processing()


def test_quote_document_and_extraction_run_lifecycles() -> None:
    values = {
        "quote_id": uuid4(),
        "storage_key": "private/q.xlsx",
        "original_file_name": "q.xlsx",
        "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "file_size": 200,
        "file_hash": "f" * 64,
        "document_type": QuoteDocumentType.XLSX,
    }
    for changes in ({"storage_key": " "}, {"file_size": 0}, {"file_hash": "bad"}):
        with pytest.raises(ValidationError):
            QuoteDocument(**{**values, **changes})
    document = QuoteDocument(**values)
    document.start_processing("ooxml", "1")
    document.start_processing("ignored", "2")
    assert document.processing_status is QuoteDocumentProcessingStatus.PROCESSING
    assert document.extractor_name == "ooxml"
    document.complete()
    document.fail(ValueError("broken workbook"))
    document.start_processing("ooxml", "2")
    assert document.last_error is None

    for changes in (
        {"idempotency_key": "bad"},
        {"extraction_fingerprint": "bad"},
        {"model": " "},
        {"run_number": 0},
    ):
        with pytest.raises(ValidationError):
            _run(**changes)
    run = _run(extraction_fingerprint="d" * 64)
    run.start()
    run.complete(
        provider_response_id="resp",
        input_tokens=-2,
        output_tokens=-3,
        estimated_cost_usd=Decimal("-1"),
        raw_response={"ok": True},
        duration_ms=-10,
    )
    assert run.status is QuoteExtractionRunStatus.COMPLETED
    assert run.input_tokens == 0 and run.estimated_cost_usd == 0
    run.start()
    assert run.status is QuoteExtractionRunStatus.COMPLETED
    run.fail(RuntimeError("provider failure"))
    run.restart()
    run.mark_approved_source()
    assert run.status is QuoteExtractionRunStatus.QUEUED and run.is_approved_source


def test_quote_item_warnings_review_snapshot_and_validation() -> None:
    for item in (
        lambda: QuoteItem(uuid4(), " ", None, None, None, None, None, None),
        lambda: QuoteItem(uuid4(), "Sensor", Decimal("0"), None, None, None, None, None),
        lambda: QuoteItem(uuid4(), "Sensor", Decimal("1"), None, None, "PESO", None, None),
        lambda: QuoteItem(uuid4(), "Sensor", Decimal("1"), None, None, None, -1, None),
        lambda: QuoteItem(
            uuid4(), "Sensor", Decimal("1"), None, None, None, None, None, source_page=0
        ),
        lambda: QuoteItem(
            uuid4(), "Sensor", Decimal("1"), None, None, None, None, None, confidence=1.1
        ),
    ):
        with pytest.raises(ValidationError):
            item()

    item = QuoteItem(
        quote_id=uuid4(),
        product_name=" Sensor A ",
        quantity=None,
        unit_price=Decimal("10"),
        total_price=Decimal("50"),
        currency=None,
        delivery_days=None,
        technical_compliance=False,
        match_status=ProductMatchStatus.POSSIBLE_MATCH,
        confidence=0.4,
        quoted_specifications={" voltage ": " 24 V ", "blank": " "},
        warnings=("OLD", "OLD"),
    )
    item.recalculate_warnings()
    assert item.compliance_status is ComplianceStatus.NON_COMPLIANT
    assert item.quoted_specifications == {"voltage": "24 V"}
    assert QuoteWarning.CURRENCY_UNKNOWN.value in item.warnings
    assert QuoteWarning.QUANTITY_UNKNOWN.value in item.warnings
    assert QuoteWarning.POSSIBLE_PRODUCT_MATCH.value in item.warnings
    assert QuoteWarning.TECHNICAL_NON_COMPLIANCE.value in item.warnings
    assert QuoteWarning.LOW_CONFIDENCE.value in item.warnings

    product_id = uuid4()
    item.apply_human_review(
        catalog_product_id=product_id,
        product_name="Reviewed Sensor",
        description="industrial",
        brand="Acme",
        model="S1",
        quantity=Decimal("2"),
        unit="piece",
        unit_price=Decimal("100"),
        total_price=Decimal("200"),
        currency="mxn",
        delivery_days=3,
        compliance_status=ComplianceStatus.COMPLIANT,
        notes="accepted",
    )
    snapshot = item.snapshot()
    assert snapshot["catalog_product_id"] == str(product_id)
    assert snapshot["currency"] == "MXN"
    assert item.technical_compliance is True
    with pytest.raises(ValidationError):
        item.apply_human_review(
            catalog_product_id=None,
            product_name=None,
            description=None,
            brand=None,
            model=None,
            quantity=Decimal("0"),
            unit=None,
            unit_price=None,
            total_price=None,
            currency=None,
            delivery_days=None,
            compliance_status=None,
            notes=None,
        )


def test_quote_task_record_retry_and_terminal_states() -> None:
    task = QuoteTaskRecord(quote_id=uuid4(), correlation_id="corr-1")
    task.start()
    task.fail(RuntimeError("temporary"), retryable=True)
    assert task.status is QuoteTaskStatus.RETRY_PENDING and task.completed_at is None
    task.start()
    task.fail(RuntimeError("permanent"), retryable=False)
    assert task.status is QuoteTaskStatus.FAILED and task.completed_at is not None
    task.succeed()
    assert task.status is QuoteTaskStatus.SUCCEEDED and task.last_error is None
