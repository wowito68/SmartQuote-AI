from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.application.services.recommendation_engine import RecommendationEngine
from app.domain.comparison.entities import Comparison, ComparisonItem, ComparisonOffer
from app.domain.comparison.value_objects import (
    ComparisonStatus,
    DeliveryTime,
    MonetaryComparisonStatus,
    Money,
    NormalizedCompliance,
    OfferStatus,
    Quantity,
    QuantityComparisonStatus,
)
from app.domain.recommendation.exceptions import RecommendationNotReady
from app.domain.recommendation.value_objects import RecommendationStatus, RecommendationWeights


def _offer(
    supplier_id: UUID,
    supplier_name: str,
    *,
    total: str | None,
    currency: str | None = "MXN",
    delivery: int | None = 5,
    compliance: NormalizedCompliance = NormalizedCompliance.COMPLIANT,
    status: OfferStatus = OfferStatus.QUOTED,
    quantity_status: QuantityComparisonStatus = QuantityComparisonStatus.MATCHED,
) -> ComparisonOffer:
    return ComparisonOffer(
        supplier_id=supplier_id,
        supplier_name=supplier_name,
        status=status,
        quote_id=uuid4() if status is OfferStatus.QUOTED else None,
        quote_item_id=uuid4() if status is OfferStatus.QUOTED else None,
        quoted_product_name="Producto" if status is OfferStatus.QUOTED else None,
        quantity=Quantity(Decimal("10"), "pieza"),
        quantity_status=quantity_status,
        total_price=Money(Decimal(total) if total is not None else None, currency),
        compliance=compliance,
        delivery=DeliveryTime(delivery, normalized=delivery is not None),
    )


def _comparison(
    rows: list[tuple[MonetaryComparisonStatus, tuple[ComparisonOffer, ...]]],
    *,
    status: ComparisonStatus = ComparisonStatus.READY,
) -> Comparison:
    comparison_id = uuid4()
    items = tuple(
        ComparisonItem(
            comparison_id=comparison_id,
            product_id=uuid4(),
            requested_product_name=f"Producto {index}",
            requested_quantity=Quantity(Decimal("10"), "pieza"),
            offers=offers,
            monetary_status=monetary_status,
        )
        for index, (monetary_status, offers) in enumerate(rows, start=1)
    )
    return Comparison(
        id=comparison_id,
        tender_id=uuid4(),
        catalog_snapshot_id=uuid4(),
        catalog_version=1,
        quotes_version="a" * 64,
        comparison_version="1.0.0",
        comparison_key="b" * 64,
        created_by_user_id=uuid4(),
        source_quote_ids=(uuid4(),),
        status=status,
        items=items,
    )


def _build(comparison: Comparison, weights: RecommendationWeights):
    return RecommendationEngine().build(
        comparison,
        weights,
        policy_version="1.0.0",
        generated_by_user_id=uuid4(),
        recommendation_key="c" * 64,
    )


def test_engine_recommends_only_complete_comparable_supplier() -> None:
    supplier_a = uuid4()
    supplier_b = uuid4()
    comparison = _comparison(
        [
            (
                MonetaryComparisonStatus.COMPARABLE,
                (
                    _offer(supplier_a, "Proveedor A", total="100", delivery=5),
                    _offer(
                        supplier_b,
                        "Proveedor B",
                        total="125",
                        delivery=10,
                        compliance=NormalizedCompliance.PARTIALLY_COMPLIANT,
                    ),
                ),
            ),
            (
                MonetaryComparisonStatus.COMPARABLE,
                (
                    _offer(supplier_a, "Proveedor A", total="200", delivery=7),
                    _offer(
                        supplier_b,
                        "Proveedor B",
                        total="250",
                        delivery=14,
                        compliance=NormalizedCompliance.PARTIALLY_COMPLIANT,
                    ),
                ),
            ),
        ]
    )

    result = _build(
        comparison,
        RecommendationWeights(Decimal("0.4"), Decimal("0.4"), Decimal("0.2")),
    )
    assert result.status is RecommendationStatus.READY
    assert result.recommended_supplier_id == supplier_a
    winner = next(
        candidate for candidate in result.candidates if candidate.supplier_id == supplier_a
    )
    assert winner.eligible is True
    assert winner.score == Decimal("100.00")
    loser = next(
        candidate for candidate in result.candidates if candidate.supplier_id == supplier_b
    )
    assert loser.score is not None and loser.score < winner.score
    assert result.human_review_required is True


def test_engine_withholds_on_top_score_tie_instead_of_arbitrary_tiebreak() -> None:
    supplier_a = uuid4()
    supplier_b = uuid4()
    comparison = _comparison(
        [
            (
                MonetaryComparisonStatus.COMPARABLE,
                (
                    _offer(supplier_a, "Proveedor A", total="100", delivery=5),
                    _offer(supplier_b, "Proveedor B", total="100", delivery=5),
                ),
            )
        ]
    )
    result = _build(
        comparison,
        RecommendationWeights(Decimal("0.4"), Decimal("0.4"), Decimal("0.2")),
    )
    assert result.status is RecommendationStatus.WITHHELD
    assert result.recommended_supplier_id is None
    assert "top_score_tie" in result.warnings


def test_zero_weight_criterion_does_not_block_on_its_missing_data() -> None:
    supplier_a = uuid4()
    supplier_b = uuid4()
    comparison = _comparison(
        [
            (
                MonetaryComparisonStatus.REQUIRES_NORMALIZATION,
                (
                    _offer(supplier_a, "Proveedor A", total=None, currency=None, delivery=4),
                    _offer(
                        supplier_b,
                        "Proveedor B",
                        total=None,
                        currency=None,
                        delivery=8,
                        compliance=NormalizedCompliance.PARTIALLY_COMPLIANT,
                    ),
                ),
            )
        ]
    )
    result = _build(
        comparison,
        RecommendationWeights(Decimal("0.7"), Decimal("0"), Decimal("0.3")),
    )
    assert result.status is RecommendationStatus.READY
    assert result.recommended_supplier_id == supplier_a
    assert all(candidate.price_score is None for candidate in result.candidates)


def test_engine_withholds_when_active_criteria_are_incomplete() -> None:
    supplier_a = uuid4()
    supplier_b = uuid4()
    comparison = _comparison(
        [
            (
                MonetaryComparisonStatus.COMPARABLE,
                (
                    _offer(
                        supplier_a,
                        "Proveedor A",
                        total="100",
                        compliance=NormalizedCompliance.UNKNOWN,
                    ),
                    _offer(
                        supplier_b,
                        "Proveedor B",
                        total="110",
                        status=OfferStatus.MISSING,
                    ),
                ),
            )
        ]
    )
    result = _build(
        comparison,
        RecommendationWeights(Decimal("0.5"), Decimal("0.5"), Decimal("0")),
    )
    assert result.status is RecommendationStatus.WITHHELD
    assert not any(candidate.eligible for candidate in result.candidates)
    reasons = {reason for candidate in result.candidates for reason in candidate.exclusion_reasons}
    assert any(reason.startswith("technical_unknown:") for reason in reasons)
    assert any(reason.startswith("missing_offer:") for reason in reasons)


def test_engine_rejects_non_ready_comparison() -> None:
    comparison = _comparison(
        [
            (
                MonetaryComparisonStatus.COMPARABLE,
                (_offer(uuid4(), "Proveedor", total="100"),),
            )
        ],
        status=ComparisonStatus.INVALID,
    )
    with pytest.raises(RecommendationNotReady, match="ready v2 comparison"):
        _build(
            comparison,
            RecommendationWeights(Decimal("1"), Decimal("0"), Decimal("0")),
        )
