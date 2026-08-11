from decimal import Decimal

import pytest

from app.domain.comparison import value_objects as comparison_values
from app.domain.quotes import value_objects as quote_values
from app.domain.shared.exceptions import ValidationError


def test_comparison_money_and_quantity_validate_completeness() -> None:
    money = comparison_values.Money(Decimal("10.50"), " mxn ")
    assert money.currency == "MXN"
    assert money.is_complete
    assert not comparison_values.Money(None, "USD").is_complete
    with pytest.raises(ValidationError):
        comparison_values.Money(Decimal("-0.01"), "MXN")
    with pytest.raises(ValidationError):
        comparison_values.Money(Decimal("1"), "PESO")

    quantity = comparison_values.Quantity(Decimal("2"), "  PIECE  ")
    assert quantity.unit == "piece"
    assert quantity.is_complete
    assert not comparison_values.Quantity(None, None).is_complete
    with pytest.raises(ValidationError):
        comparison_values.Quantity(Decimal("-1"), "piece")


def test_comparison_delivery_preserves_ambiguous_text_without_inference() -> None:
    ambiguous = comparison_values.DeliveryTime(None, "  despues   de confirmar  ")
    assert ambiguous.original_text == "despues de confirmar"
    assert ambiguous.normalized is False
    assert ambiguous.is_known
    assert not comparison_values.DeliveryTime(None).is_known
    with pytest.raises(ValidationError):
        comparison_values.DeliveryTime(-1)


def test_quote_money_quantity_unit_and_confidence_reject_invalid_values() -> None:
    with pytest.raises(ValidationError):
        quote_values.Money("not-a-number", "MXN")
    with pytest.raises(ValidationError):
        quote_values.Money(Decimal("10"), "PESO")
    with pytest.raises(ValidationError):
        quote_values.Quantity("not-a-number")
    with pytest.raises(ValidationError):
        quote_values.Unit("   ")
    with pytest.raises(ValidationError):
        quote_values.confidence_band(1.1)
    with pytest.raises(ValueError):
        quote_values.confidence_band(0.8, high=0.7, medium=0.9)

    assert quote_values.Money("10.25", " mxn ").currency == "MXN"
    assert quote_values.Quantity("2").value == Decimal("2")
    assert quote_values.Unit(" piezas ").value == "piece"
    assert quote_values.confidence_band(0.95) == "high"
    assert quote_values.confidence_band(0.8) == "medium"
    assert quote_values.confidence_band(0.5) == "low"
