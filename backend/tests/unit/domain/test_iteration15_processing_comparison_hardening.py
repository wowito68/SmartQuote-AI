from decimal import Decimal
from uuid import uuid4

import pytest

from app.domain.comparison.entities import (
    Comparison,
    ComparisonItem,
    ComparisonOffer,
    ComparisonWarning,
)
from app.domain.comparison.value_objects import (
    ComparisonStatus,
    ComparisonWarningCode,
    DeliveryTime,
    MonetaryComparisonStatus,
    Money,
    NormalizedCompliance,
    OfferStatus,
    Quantity,
    QuantityComparisonStatus,
    WarningSeverity,
)
from app.domain.documents.processing import DocumentPage, DocumentQuality, ExtractionRun
from app.domain.documents.value_objects import (
    DocumentQualityDecision,
    DocumentQualityLevel,
    ExtractionRunStatus,
)
from app.domain.shared.exceptions import ValidationError


def test_document_processing_entities_cover_success_failure_and_reuse() -> None:
    for page_args in (
        (uuid4(), uuid4(), 0, "text", 10, 10, 0),
        (uuid4(), uuid4(), 1, "text", 0, 10, 0),
        (uuid4(), uuid4(), 1, "text", 10, 10, -1),
    ):
        with pytest.raises(ValidationError):
            DocumentPage(*page_args)
    page = DocumentPage(uuid4(), uuid4(), 1, "hello world", 612, 792, 5)
    assert page.character_count == 11
    assert page.word_count == 2
    assert not page.is_empty
    assert page.text_density > 0

    with pytest.raises(ValidationError):
        ExtractionRun(uuid4(), "bad", "pdf", "1", {})
    with pytest.raises(ValidationError):
        ExtractionRun(uuid4(), "a" * 64, " ", "1", {})
    run = ExtractionRun(uuid4(), "a" * 64, "pdf", "1", {})
    run.complete([page], -5)
    assert run.status is ExtractionRunStatus.COMPLETED and run.duration_ms == 0
    run.restart()
    assert run.status is ExtractionRunStatus.RUNNING and run.pages_processed == 0
    run.fail(RuntimeError("extractor failed"))
    assert run.error_type == "RuntimeError"
    source_id = uuid4()
    run.mark_reused(source_id)
    assert run.status is ExtractionRunStatus.REUSED
    assert run.reused_from_run_id == source_id

    values = {
        "document_id": uuid4(),
        "extraction_run_id": uuid4(),
        "pages_processed": 2,
        "empty_pages": 1,
        "characters_extracted": 100,
        "empty_page_percentage": 50.0,
        "text_density": 3.0,
        "quality_level": DocumentQualityLevel.MEDIUM,
        "decision": DocumentQualityDecision.READY_FOR_AI,
        "requires_manual_review": False,
    }
    assert DocumentQuality(**values).pages_processed == 2
    for changes in (
        {"pages_processed": -1},
        {"empty_pages": 3},
        {"empty_page_percentage": 101},
        {"text_density": -1},
    ):
        with pytest.raises(ValidationError):
            DocumentQuality(**{**values, **changes})


def test_comparison_offer_item_serialization_and_validation() -> None:
    warning = ComparisonWarning(
        ComparisonWarningCode.MISSING_PRICE,
        WarningSeverity.WARNING,
        " missing price ",
        supplier_id=uuid4(),
    )
    assert warning.as_dict()["code"] == "missing_price"
    with pytest.raises(ValidationError):
        ComparisonWarning(
            ComparisonWarningCode.MISSING_PRICE,
            WarningSeverity.WARNING,
            " ",
        )

    offer = ComparisonOffer(
        supplier_id=uuid4(),
        supplier_name=" Acme ",
        status=OfferStatus.QUOTED,
        quote_id=uuid4(),
        quote_item_id=uuid4(),
        quoted_product_name="Sensor",
        brand="Acme",
        model="S1",
        quantity=Quantity(Decimal("2"), " Piece "),
        quantity_status=QuantityComparisonStatus.MATCHED,
        unit_price=Money(Decimal("100"), "mxn"),
        total_price=Money(Decimal("200"), "MXN"),
        compliance=NormalizedCompliance.COMPLIANT,
        delivery=DeliveryTime(3),
        confidence=0.9,
        warnings=(warning,),
    )
    assert offer.as_dict()["currency"] == "MXN"
    with pytest.raises(ValidationError):
        ComparisonOffer(uuid4(), " ", OfferStatus.MISSING)
    with pytest.raises(ValidationError):
        ComparisonOffer(uuid4(), "Acme", OfferStatus.QUOTED, confidence=1.1)
    with pytest.raises(ValidationError):
        ComparisonOffer(
            uuid4(),
            "Acme",
            OfferStatus.MISSING,
            quote_item_id=uuid4(),
            quoted_product_name="Sensor",
        )

    comparison_id = uuid4()
    item = ComparisonItem(
        comparison_id=comparison_id,
        product_id=uuid4(),
        requested_product_name=" Sensor ",
        requested_quantity=Quantity(Decimal("2"), "piece"),
        offers=(offer,),
        monetary_status=MonetaryComparisonStatus.COMPARABLE,
    )
    assert item.as_dict()["requested_product"] == "Sensor"
    with pytest.raises(ValidationError):
        ComparisonItem(
            comparison_id,
            uuid4(),
            " ",
            Quantity(None, None),
            (),
            MonetaryComparisonStatus.INSUFFICIENT_DATA,
        )
    with pytest.raises(ValidationError):
        ComparisonItem(
            comparison_id,
            uuid4(),
            "Sensor",
            Quantity(None, None),
            (offer, offer),
            MonetaryComparisonStatus.COMPARABLE,
        )


def test_comparison_ready_invalid_and_archive_lifecycles() -> None:
    offer = ComparisonOffer(uuid4(), "Acme", OfferStatus.MISSING)
    item = ComparisonItem(
        comparison_id=uuid4(),
        product_id=uuid4(),
        requested_product_name="Sensor",
        requested_quantity=Quantity(None, None),
        offers=(offer,),
        monetary_status=MonetaryComparisonStatus.INSUFFICIENT_DATA,
    )
    comparison = Comparison(
        tender_id=uuid4(),
        catalog_snapshot_id=uuid4(),
        catalog_version=1,
        quotes_version="a" * 64,
        comparison_version="1.0",
        comparison_key="b" * 64,
        created_by_user_id=uuid4(),
        source_quote_ids=(uuid4(),),
    )
    with pytest.raises(ValidationError):
        comparison.complete((item,), ())
    comparison.start()
    comparison.complete((item,), ())
    assert comparison.status is ComparisonStatus.READY
    assert comparison.as_dict()["items"][0]["offers"][0]["status"] == "missing"
    comparison.archive()
    assert comparison.status is ComparisonStatus.ARCHIVED
    with pytest.raises(ValidationError):
        comparison.start()

    critical = ComparisonWarning(
        ComparisonWarningCode.DUPLICATE_QUOTE_ITEM,
        WarningSeverity.CRITICAL,
        "duplicate item",
    )
    invalid_offer = ComparisonOffer(
        uuid4(), "Acme", OfferStatus.MISSING, warnings=(critical,)
    )
    invalid_item = ComparisonItem(
        comparison_id=uuid4(),
        product_id=uuid4(),
        requested_product_name="Sensor",
        requested_quantity=Quantity(None, None),
        offers=(invalid_offer,),
        monetary_status=MonetaryComparisonStatus.INSUFFICIENT_DATA,
    )
    invalid = Comparison(
        tender_id=uuid4(),
        catalog_snapshot_id=uuid4(),
        catalog_version=1,
        quotes_version="c" * 64,
        comparison_version="1.0",
        comparison_key="d" * 64,
        created_by_user_id=uuid4(),
        source_quote_ids=(),
    )
    invalid.start()
    invalid.complete((invalid_item,), ())
    assert invalid.status is ComparisonStatus.INVALID
    invalid.archive()

    for changes in (
        {"catalog_version": 0},
        {"quotes_version": "bad"},
        {"comparison_version": " "},
    ):
        values = {
            "tender_id": uuid4(),
            "catalog_snapshot_id": uuid4(),
            "catalog_version": 1,
            "quotes_version": "a" * 64,
            "comparison_version": "1.0",
            "comparison_key": "b" * 64,
            "created_by_user_id": uuid4(),
            "source_quote_ids": (),
        }
        values.update(changes)
        with pytest.raises(ValidationError):
            Comparison(**values)
