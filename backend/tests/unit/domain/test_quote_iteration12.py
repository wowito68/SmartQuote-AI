from decimal import Decimal
from uuid import uuid4

import pytest

from app.domain.quotes.entities import Quote, QuoteItem
from app.domain.quotes.exceptions import InvalidQuoteState
from app.domain.quotes.value_objects import (
    ComplianceStatus,
    DeliveryTime,
    Money,
    ProductMatchStatus,
    Quantity,
    QuoteWarning,
    Unit,
    confidence_band,
)
from app.domain.shared.exceptions import ValidationError


def make_quote() -> Quote:
    return Quote(
        tender_id=uuid4(),
        tender_supplier_id=uuid4(),
        supplier_id=uuid4(),
        original_file_name="quote.pdf",
        storage_key="private/quote.pdf",
        mime_type="application/pdf",
        file_size=100,
        file_hash="a" * 64,
        uploaded_by_user_id=uuid4(),
    )


def test_value_objects_reject_invalid_values_and_normalize_units() -> None:
    assert Money(Decimal("0"), "mxn").currency == "MXN"
    assert Quantity(Decimal("2.5")).value == Decimal("2.5")
    assert Unit("PZAS").value == "piece"
    assert DeliveryTime(0).days == 0

    with pytest.raises(ValidationError):
        Money(Decimal("-1"), "MXN")
    with pytest.raises(ValidationError):
        Quantity(Decimal("0"))
    with pytest.raises(ValidationError):
        DeliveryTime(-1)


def test_confidence_bands_use_centralized_thresholds() -> None:
    assert confidence_band(0.90) == "high"
    assert confidence_band(0.70) == "medium"
    assert confidence_band(0.69) == "low"


def test_missing_price_remains_unknown_and_is_never_derived() -> None:
    item = QuoteItem(
        quote_id=uuid4(),
        product_name="Sensor",
        quantity=Decimal("2"),
        unit_price=None,
        total_price=None,
        currency=None,
        delivery_days=None,
        technical_compliance=None,
        confidence=0.95,
    )
    item.recalculate_warnings()

    assert item.unit_price is None
    assert item.total_price is None
    assert QuoteWarning.PRICE_NOT_FOUND.value in item.warnings


def test_inconsistent_price_generates_warning_without_correction() -> None:
    item = QuoteItem(
        quote_id=uuid4(),
        product_name="Sensor",
        quantity=Decimal("2"),
        unit_price=Decimal("100"),
        total_price=Decimal("250"),
        currency="MXN",
        delivery_days=3,
        technical_compliance=True,
        compliance_status=ComplianceStatus.COMPLIANT,
        match_status=ProductMatchStatus.MATCHED,
        match_score=1.0,
        confidence=0.95,
    )
    item.recalculate_warnings()

    assert item.total_price == Decimal("250")
    assert QuoteWarning.PRICE_CALCULATION_MISMATCH.value in item.warnings


def test_approved_quote_cannot_be_reprocessed_silently() -> None:
    quote = make_quote()
    quote.start_validation()
    quote.start_extraction()
    quote.mark_extracted()
    quote.mark_normalized()
    quote.start_review()
    quote.approve(uuid4())

    with pytest.raises(InvalidQuoteState):
        quote.restart_processing()
