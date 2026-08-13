from decimal import Decimal
from uuid import uuid4

import pytest

from app.domain.recommendation.entities import Recommendation, RecommendationCandidate
from app.domain.recommendation.value_objects import RecommendationStatus, RecommendationWeights
from app.domain.shared.exceptions import ValidationError


def _candidate(*, eligible: bool = True) -> RecommendationCandidate:
    return RecommendationCandidate(
        supplier_id=uuid4(),
        supplier_name=" Proveedor Uno ",
        eligible=eligible,
        product_count=2,
        technical_score=Decimal("100"),
        price_score=Decimal("90"),
        delivery_score=Decimal("80"),
        score=Decimal("92") if eligible else None,
        exclusion_reasons=() if eligible else ("missing_offer:1", "missing_offer:1"),
    )


def test_recommendation_weights_are_explicit_and_canonical() -> None:
    weights = RecommendationWeights(Decimal("0.4"), Decimal("0.35"), Decimal("0.25"))
    assert weights.canonical() == "0.4|0.35|0.25"
    assert weights.as_dict() == {
        "technical": "0.4",
        "price": "0.35",
        "delivery": "0.25",
    }

    with pytest.raises(ValidationError, match="sum to one"):
        RecommendationWeights(Decimal("0.4"), Decimal("0.4"), Decimal("0.4"))
    with pytest.raises(ValidationError, match="between zero and one"):
        RecommendationWeights(Decimal("1.1"), Decimal("-0.1"), Decimal("0"))


def test_candidate_and_recommendation_invariants_prevent_hidden_winners() -> None:
    candidate = _candidate()
    assert candidate.supplier_name == "Proveedor Uno"

    with pytest.raises(ValidationError, match="Eligible recommendation"):
        RecommendationCandidate(
            supplier_id=uuid4(),
            supplier_name="Proveedor",
            eligible=True,
            product_count=1,
            technical_score=None,
            price_score=None,
            delivery_score=None,
            score=None,
        )

    ready = Recommendation(
        comparison_id=uuid4(),
        tender_id=uuid4(),
        recommendation_key="a" * 64,
        policy_version="1.0.0",
        weights=RecommendationWeights(Decimal("1"), Decimal("0"), Decimal("0")),
        generated_by_user_id=uuid4(),
        status=RecommendationStatus.READY,
        candidates=(candidate,),
        recommended_supplier_id=candidate.supplier_id,
        recommended_supplier_name=candidate.supplier_name,
        explanation=" Highest deterministic score. ",
    )
    assert ready.human_review_required is True
    assert ready.explanation == "Highest deterministic score."

    with pytest.raises(ValidationError, match="Withheld recommendations"):
        Recommendation(
            comparison_id=uuid4(),
            tender_id=uuid4(),
            recommendation_key="b" * 64,
            policy_version="1.0.0",
            weights=RecommendationWeights(Decimal("1"), Decimal("0"), Decimal("0")),
            generated_by_user_id=uuid4(),
            status=RecommendationStatus.WITHHELD,
            candidates=(_candidate(eligible=False),),
            recommended_supplier_id=uuid4(),
            recommended_supplier_name="No debe existir",
            explanation="Withheld.",
        )
