from decimal import Decimal
from uuid import uuid4

import pytest

from app.domain.quotes.entities import Quote, QuoteExtractionRun, QuoteItem
from app.domain.quotes.exceptions import InvalidQuoteState
from app.domain.quotes.value_objects import QuoteExtractionRunStatus, QuoteStatus


def quote() -> Quote:
    return Quote(
        tender_id=uuid4(),
        tender_supplier_id=uuid4(),
        supplier_id=uuid4(),
        original_file_name="supplier.pdf",
        storage_key="private/tender/supplier.pdf",
        mime_type="application/pdf",
        file_size=100,
        file_hash="a" * 64,
        uploaded_by_user_id=uuid4(),
    )


def test_quote_state_machine_requires_sequential_review_flow() -> None:
    item = quote()
    with pytest.raises(InvalidQuoteState):
        item.approve(uuid4())

    item.start_validation()
    item.start_extraction()
    item.mark_extracted()
    item.mark_normalized()
    item.start_review()
    item.approve(uuid4())
    item.include_in_comparison()

    assert item.status is QuoteStatus.INCLUDED_IN_COMPARISON
    with pytest.raises(InvalidQuoteState):
        item.start_extraction()


def test_quote_rejection_requires_pending_review_and_reason() -> None:
    item = quote()
    item.start_validation()
    item.start_extraction()
    item.mark_extracted()
    item.mark_normalized()
    item.start_review()
    item.reject(uuid4(), "Does not meet technical requirements")
    assert item.status is QuoteStatus.REJECTED
    assert item.rejection_reason == "Does not meet technical requirements"


def test_quote_item_calculates_total_and_preserves_evidence() -> None:
    item = QuoteItem(
        quote_id=uuid4(),
        product_name="Cable THW 12 AWG",
        quantity=Decimal("10"),
        unit_price=Decimal("125.50"),
        total_price=None,
        currency="mxn",
        delivery_days=5,
        technical_compliance=True,
        source_page=2,
        evidence_fragment="Cable THW 12 AWG 10 125.50",
        confidence=0.93,
    )
    assert item.total_price == Decimal("1255.00")
    assert item.currency == "MXN"
    assert item.source_page == 2


def test_quote_extraction_run_records_cost_and_safe_retry() -> None:
    run = QuoteExtractionRun(
        quote_id=uuid4(),
        tender_id=uuid4(),
        supplier_id=uuid4(),
        idempotency_key="b" * 64,
        extractor_version="fallback-1",
        prompt_version="1.0.0",
        model="gpt-test",
        schema_version="1.0.0",
        schema_hash="c" * 64,
    )
    run.start()
    run.fail(RuntimeError("temporary"))
    assert run.status is QuoteExtractionRunStatus.FAILED
    run.restart()
    assert run.status is QuoteExtractionRunStatus.QUEUED
    run.start()
    run.complete(
        provider_response_id="resp_1",
        input_tokens=100,
        output_tokens=20,
        estimated_cost_usd=Decimal("0.001234"),
        raw_response={"items": []},
    )
    assert run.status is QuoteExtractionRunStatus.COMPLETED
    assert run.estimated_cost_usd == Decimal("0.001234")
