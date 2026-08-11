from decimal import Decimal

import pytest

from app.domain.comparison.value_objects import (
    DeliveryTime as ComparisonDeliveryTime,
    Money as ComparisonMoney,
    Quantity as ComparisonQuantity,
)
from app.domain.quotes.value_objects import (
    Money as QuoteMoney,
    Quantity as QuoteQuantity,
    Unit,
    confidence_band,
)
from app.domain.shared.exceptions import ValidationError


def test_comparison_money_and_quantity_validate_completeness() -> None:
    money = ComparisonMoney(Decimal("10.50"), " mxn ")
    assert money.currency == "MXN"
    assert money.is_complete
    assert not ComparisonMoney(None, "USD").is_complete
    with pytest.raises(ValidationError):
        ComparisonMoney(Decimal("-0.01"), "MXN")
    with pytest.raises(ValidationError):
        ComparisonMoney(Decimal("1"), "PESO")

    quantity = ComparisonQuantity(Decimal("2"), "  PIECE  ")
    assert quantity.unit == "piece"
    assert quantity.is_complete
    assert not ComparisonQuantity(None, None).is_complete
    with pytest.raises(ValidationError):
        ComparisonQuantity(Decimal("-1"), "piece")


def test_comparison_delivery_preserves_ambiguous_text_without_inference() -> None:
    ambiguous = ComparisonDeliveryTime(None, "  despues   de confirmar  ")
    assert ambiguous.original_text == "despues de confirmar"
    assert ambiguous.normalized is False
    assert ambiguous.is_known
    assert not ComparisonDeliveryTime(None).is_known
    with pytest.raises(ValidationError):
        ComparisonDeliveryTime(-1)


def test_quote_money_quantity_unit_and_confidence_reject_invalid_values() -> None:
    with pytest.raises(ValidationError):
        QuoteMoney("not-a-number", "MXN")
    with pytest.raises(ValidationError):
        QuoteMoney(Decimal("10"), "PESO")
    with pytest.raises(ValidationError):
        QuoteQuantity("not-a-number")
    with pytest.raises(ValidationError):
        Unit("   ")
    with pytest.raises(ValidationError):
        confidence_band(1.1)
    with pytest.raises(ValueError):
        confidence_band(0.8, high=0.7, medium=0.9)

    assert QuoteMoney("10.25", " mxn ").currency == "MXN"
    assert QuoteQuantity("2").value == Decimal("2")
    assert Unit(" piezas ").value == "piece"
    assert confidence_band(0.95) == "high"
    assert confidence_band(0.8) == "medium"
    assert confidence_band(0.5) == "low"
