from decimal import Decimal
from uuid import uuid4

from app.application.services.quote_matching import (
    QuoteProductMatcher,
    TechnicalComplianceEvaluator,
)
from app.domain.quotes.value_objects import ComplianceStatus, ProductMatchStatus


def product(name: str, *, specifications: dict[str, str] | None = None) -> dict:
    return {
        "product_id": str(uuid4()),
        "name": name,
        "description": "Sensor para planta industrial",
        "category": "sensores",
        "quantity": "2",
        "unit": "piece",
        "specifications": specifications or {},
    }


def test_product_matching_returns_status_score_and_reason() -> None:
    matcher = QuoteProductMatcher()
    requested = product("Sensor temperatura industrial")

    exact = matcher.match(
        (requested,),
        name="Sensor temperatura industrial",
        description=None,
        brand="XYZ",
        model="T-100",
        unit="piece",
        quantity=Decimal("2"),
    )
    assert exact.status is ProductMatchStatus.MATCHED
    assert exact.score == 1.0
    assert exact.reason

    unmatched = matcher.match(
        (requested,),
        name="Bomba centrifuga",
        description="Equipo hidraulico",
        brand=None,
        model=None,
        unit=None,
        quantity=None,
    )
    assert unmatched.status is ProductMatchStatus.UNMATCHED
    assert unmatched.product_id is None


def test_technical_compliance_never_assumes_missing_information() -> None:
    evaluator = TechnicalComplianceEvaluator()
    requested = {"proteccion": "IP67", "voltaje": "24V"}

    status, _ = evaluator.evaluate(requested, {})
    assert status is ComplianceStatus.UNKNOWN

    status, _ = evaluator.evaluate(requested, {"proteccion": "IP65"})
    assert status is ComplianceStatus.NON_COMPLIANT

    status, _ = evaluator.evaluate(requested, {"proteccion": "IP67"})
    assert status is ComplianceStatus.PARTIAL

    status, _ = evaluator.evaluate(
        requested,
        {"proteccion": "IP67", "voltaje": "24V"},
    )
    assert status is ComplianceStatus.COMPLIANT
