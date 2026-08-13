from collections import defaultdict
from decimal import Decimal
from uuid import UUID

from app.domain.comparison.entities import Comparison, ComparisonItem, ComparisonOffer
from app.domain.comparison.value_objects import (
    ComparisonStatus,
    MonetaryComparisonStatus,
    NormalizedCompliance,
    OfferStatus,
    QuantityComparisonStatus,
)
from app.domain.recommendation.entities import Recommendation, RecommendationCandidate
from app.domain.recommendation.exceptions import RecommendationNotReady
from app.domain.recommendation.value_objects import RecommendationStatus, RecommendationWeights

_SCORE_SCALE = Decimal("100")
_PARTIAL_COMPLIANCE = Decimal("0.5")


class RecommendationEngine:
    """Build a conservative, deterministic recommendation from Comparison v2 only."""

    def build(
        self,
        comparison: Comparison,
        weights: RecommendationWeights,
        *,
        policy_version: str,
        generated_by_user_id: UUID,
        recommendation_key: str,
    ) -> Recommendation:
        if comparison.status is not ComparisonStatus.READY:
            raise RecommendationNotReady("Recommendation requires a ready v2 comparison.")
        if not comparison.items:
            raise RecommendationNotReady("Recommendation requires comparison items.")

        supplier_names = self._supplier_names(comparison)
        if not supplier_names:
            raise RecommendationNotReady("Recommendation requires at least one supplier.")

        price_baselines = {
            item.id: self._minimum_price(item) if weights.price > 0 else None
            for item in comparison.items
        }
        delivery_baselines = {
            item.id: self._minimum_delivery(item) if weights.delivery > 0 else None
            for item in comparison.items
        }
        candidates = tuple(
            self._candidate(
                comparison,
                supplier_id,
                supplier_name,
                weights,
                price_baselines,
                delivery_baselines,
            )
            for supplier_id, supplier_name in sorted(
                supplier_names.items(), key=lambda value: (value[1].casefold(), str(value[0]))
            )
        )
        eligible = sorted(
            (candidate for candidate in candidates if candidate.eligible),
            key=lambda candidate: (
                -(candidate.score or Decimal("0")),
                candidate.supplier_name.casefold(),
                str(candidate.supplier_id),
            ),
        )
        warnings = tuple(
            sorted(
                {
                    f"source_comparison_warning:{warning.code.value}"
                    for warning in comparison.warnings
                }
            )
        )

        if not eligible:
            return Recommendation(
                comparison_id=comparison.id,
                tender_id=comparison.tender_id,
                recommendation_key=recommendation_key,
                policy_version=policy_version,
                weights=weights,
                generated_by_user_id=generated_by_user_id,
                status=RecommendationStatus.WITHHELD,
                candidates=candidates,
                recommended_supplier_id=None,
                recommended_supplier_name=None,
                explanation=(
                    "Recommendation withheld because no supplier satisfies all active "
                    "criteria with comparable data across every requested product."
                ),
                warnings=warnings,
            )

        top_score = eligible[0].score
        tied = [candidate for candidate in eligible if candidate.score == top_score]
        if len(tied) > 1:
            tied_names = ", ".join(candidate.supplier_name for candidate in tied)
            return Recommendation(
                comparison_id=comparison.id,
                tender_id=comparison.tender_id,
                recommendation_key=recommendation_key,
                policy_version=policy_version,
                weights=weights,
                generated_by_user_id=generated_by_user_id,
                status=RecommendationStatus.WITHHELD,
                candidates=candidates,
                recommended_supplier_id=None,
                recommended_supplier_name=None,
                explanation=(
                    "Recommendation withheld because the highest deterministic score is tied "
                    f"between: {tied_names}. Human review is required."
                ),
                warnings=warnings + ("top_score_tie",),
            )

        winner = eligible[0]
        return Recommendation(
            comparison_id=comparison.id,
            tender_id=comparison.tender_id,
            recommendation_key=recommendation_key,
            policy_version=policy_version,
            weights=weights,
            generated_by_user_id=generated_by_user_id,
            status=RecommendationStatus.READY,
            candidates=candidates,
            recommended_supplier_id=winner.supplier_id,
            recommended_supplier_name=winner.supplier_name,
            explanation=(
                f"{winner.supplier_name} has the highest deterministic score ({winner.score}) "
                "among suppliers with complete comparable data for every active criterion. "
                "This is advisory only and requires human review before any award decision."
            ),
            warnings=warnings,
        )

    def _candidate(
        self,
        comparison: Comparison,
        supplier_id: UUID,
        supplier_name: str,
        weights: RecommendationWeights,
        price_baselines: dict[UUID, Decimal | None],
        delivery_baselines: dict[UUID, int | None],
    ) -> RecommendationCandidate:
        reasons: list[str] = []
        technical_scores: list[Decimal] = []
        price_scores: list[Decimal] = []
        delivery_scores: list[Decimal] = []

        for item in comparison.items:
            offer = next(
                (candidate for candidate in item.offers if candidate.supplier_id == supplier_id),
                None,
            )
            prefix = str(item.product_id)
            if offer is None or offer.status is OfferStatus.MISSING:
                reasons.append(f"missing_offer:{prefix}")
                continue
            if offer.status is OfferStatus.INVALID:
                reasons.append(f"invalid_offer:{prefix}")
                continue
            if offer.quantity_status is not QuantityComparisonStatus.MATCHED:
                reasons.append(f"quantity_not_matched:{prefix}")
            if offer.compliance is NormalizedCompliance.NON_COMPLIANT:
                reasons.append(f"non_compliant:{prefix}")

            if weights.technical > 0:
                technical = self._technical_score(offer)
                if technical is None:
                    reasons.append(f"technical_unknown:{prefix}")
                else:
                    technical_scores.append(technical)

            if weights.price > 0:
                price = self._price_score(item, offer, price_baselines[item.id])
                if price is None:
                    reasons.append(f"price_not_comparable:{prefix}")
                else:
                    price_scores.append(price)

            if weights.delivery > 0:
                delivery = self._delivery_score(offer, delivery_baselines[item.id])
                if delivery is None:
                    reasons.append(f"delivery_not_comparable:{prefix}")
                else:
                    delivery_scores.append(delivery)

        unique_reasons = tuple(sorted(set(reasons)))
        if unique_reasons:
            return RecommendationCandidate(
                supplier_id=supplier_id,
                supplier_name=supplier_name,
                eligible=False,
                product_count=len(comparison.items),
                technical_score=self._average_percent(technical_scores),
                price_score=self._average_percent(price_scores),
                delivery_score=self._average_percent(delivery_scores),
                score=None,
                exclusion_reasons=unique_reasons,
            )

        technical = self._average_ratio(technical_scores) if weights.technical > 0 else Decimal("0")
        price = self._average_ratio(price_scores) if weights.price > 0 else Decimal("0")
        delivery = self._average_ratio(delivery_scores) if weights.delivery > 0 else Decimal("0")
        score = (
            technical * weights.technical
            + price * weights.price
            + delivery * weights.delivery
        ) * _SCORE_SCALE
        return RecommendationCandidate(
            supplier_id=supplier_id,
            supplier_name=supplier_name,
            eligible=True,
            product_count=len(comparison.items),
            technical_score=(technical * _SCORE_SCALE).quantize(Decimal("0.01"))
            if weights.technical > 0
            else None,
            price_score=(price * _SCORE_SCALE).quantize(Decimal("0.01"))
            if weights.price > 0
            else None,
            delivery_score=(delivery * _SCORE_SCALE).quantize(Decimal("0.01"))
            if weights.delivery > 0
            else None,
            score=score.quantize(Decimal("0.01")),
        )

    @staticmethod
    def _supplier_names(comparison: Comparison) -> dict[UUID, str]:
        names: dict[UUID, str] = {}
        for item in comparison.items:
            for offer in item.offers:
                names.setdefault(offer.supplier_id, offer.supplier_name)
        return names

    @staticmethod
    def _minimum_price(item: ComparisonItem) -> Decimal | None:
        if item.monetary_status is not MonetaryComparisonStatus.COMPARABLE:
            return None
        values = [
            offer.total_price.amount
            for offer in item.offers
            if offer.status is OfferStatus.QUOTED
            and offer.total_price.amount is not None
            and offer.total_price.currency is not None
        ]
        return min(values) if values else None

    @staticmethod
    def _minimum_delivery(item: ComparisonItem) -> int | None:
        values = [
            offer.delivery.days
            for offer in item.offers
            if offer.status is OfferStatus.QUOTED
            and offer.delivery.normalized
            and offer.delivery.days is not None
        ]
        return min(values) if values else None

    @staticmethod
    def _technical_score(offer: ComparisonOffer) -> Decimal | None:
        if offer.compliance is NormalizedCompliance.COMPLIANT:
            return Decimal("1")
        if offer.compliance is NormalizedCompliance.PARTIALLY_COMPLIANT:
            return _PARTIAL_COMPLIANCE
        return None

    @staticmethod
    def _price_score(
        item: ComparisonItem,
        offer: ComparisonOffer,
        minimum: Decimal | None,
    ) -> Decimal | None:
        amount = offer.total_price.amount
        if (
            item.monetary_status is not MonetaryComparisonStatus.COMPARABLE
            or amount is None
            or offer.total_price.currency is None
            or minimum is None
        ):
            return None
        if minimum == 0:
            return Decimal("1") if amount == 0 else Decimal("0")
        if amount <= 0:
            return None
        return min(Decimal("1"), minimum / amount)

    @staticmethod
    def _delivery_score(offer: ComparisonOffer, minimum: int | None) -> Decimal | None:
        days = offer.delivery.days
        if not offer.delivery.normalized or days is None or minimum is None:
            return None
        if minimum == 0:
            return Decimal("1") if days == 0 else Decimal("0")
        if days <= 0:
            return None
        return min(Decimal("1"), Decimal(minimum) / Decimal(days))

    @staticmethod
    def _average_ratio(values: list[Decimal]) -> Decimal:
        if not values:
            return Decimal("0")
        return sum(values, Decimal("0")) / Decimal(len(values))

    @classmethod
    def _average_percent(cls, values: list[Decimal]) -> Decimal | None:
        if not values:
            return None
        return (cls._average_ratio(values) * _SCORE_SCALE).quantize(Decimal("0.01"))
