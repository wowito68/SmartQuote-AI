from decimal import Decimal
from uuid import uuid4

from app.application.services.comparison_engine import ComparisonEngine
from app.domain.quotes.entities import QuoteItem
from app.domain.quotes.value_objects import ComplianceStatus, ProductMatchStatus


def _item(currency: str, price: str) -> QuoteItem:
    return QuoteItem(
        quote_id=uuid4(),
        catalog_product_id=uuid4(),
        product_name="Sensor industrial",
        quantity=Decimal("1"),
        unit="piece",
        unit_price=Decimal(price),
        total_price=Decimal(price),
        currency=currency,
        delivery_days=5,
        technical_compliance=True,
        compliance_status=ComplianceStatus.COMPLIANT,
        match_status=ProductMatchStatus.MATCHED,
        match_score=1.0,
        confidence=0.99,
    )


def test_comparison_does_not_apply_implicit_fx_conversion() -> None:
    product_id = uuid4()
    mxn = _item("MXN", "1000")
    usd = _item("USD", "50")
    mxn.catalog_product_id = product_id
    usd.catalog_product_id = product_id

    rows, recommendation = ComparisonEngine().build(
        [
            ("supplier-mxn", "Proveedor MXN", mxn),
            ("supplier-usd", "Proveedor USD", usd),
        ]
    )

    assert {row["currency"] for row in rows} == {"MXN", "USD"}
    assert all(row["criteria"]["price"] == 0.5 for row in rows)
    assert any(
        "Currencies differ" in warning
        for warning in recommendation["warnings"]
    )
