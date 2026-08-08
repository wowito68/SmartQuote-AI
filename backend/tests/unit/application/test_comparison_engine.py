from decimal import Decimal
from uuid import uuid4

from app.application.services.comparison_engine import ComparisonEngine
from app.domain.quotes.entities import QuoteItem


def item(
    *,
    quote_id,
    product_id,
    price: str,
    delivery: int,
    compliance: bool | None,
) -> QuoteItem:
    return QuoteItem(
        quote_id=quote_id,
        catalog_product_id=product_id,
        product_name="Switch 48 ports",
        quantity=Decimal("1"),
        unit_price=Decimal(price),
        total_price=Decimal(price),
        currency="USD",
        delivery_days=delivery,
        technical_compliance=compliance,
        source_page=1,
        evidence_fragment="Switch 48 ports",
        confidence=0.9,
    )


def test_comparison_is_deterministic_and_requires_human_review() -> None:
    product_id = uuid4()
    first = item(
        quote_id=uuid4(),
        product_id=product_id,
        price="1000",
        delivery=10,
        compliance=True,
    )
    second = item(
        quote_id=uuid4(),
        product_id=product_id,
        price="900",
        delivery=15,
        compliance=True,
    )
    engine = ComparisonEngine()
    entries = [
        ("supplier-a", "Alpha", first),
        ("supplier-b", "Beta", second),
    ]

    rows_a, recommendation_a = engine.build(entries)
    rows_b, recommendation_b = engine.build(entries)

    assert rows_a == rows_b
    assert recommendation_a == recommendation_b
    assert recommendation_a["human_review_required"] is True
    assert recommendation_a["decision"] == "recommendation_only"
    assert recommendation_a["recommended_supplier_id"] in {"supplier-a", "supplier-b"}
    assert recommendation_a["criteria"] == {
        "technical_compliance_weight": 0.5,
        "price_weight": 0.35,
        "delivery_weight": 0.15,
    }


def test_comparison_warns_when_ai_data_is_incomplete() -> None:
    quote_id = uuid4()
    product_id = uuid4()
    incomplete = QuoteItem(
        quote_id=quote_id,
        catalog_product_id=product_id,
        product_name="Firewall",
        quantity=Decimal("1"),
        unit_price=None,
        total_price=None,
        currency="USD",
        delivery_days=None,
        technical_compliance=None,
        source_page=2,
        evidence_fragment="Firewall",
        confidence=0.5,
    )

    rows, recommendation = ComparisonEngine().build(
        [("supplier-a", "Alpha", incomplete)]
    )

    assert rows[0]["source"]["quote_id"] == str(quote_id)
    assert rows[0]["warnings"]
    assert len(recommendation["warnings"]) == 3
