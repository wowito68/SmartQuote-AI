import hashlib
from uuid import UUID

from app.application.dtos.recommendation import (
    RecommendationCandidateResponse,
    RecommendationResponse,
    RecommendationWeightsResponse,
)
from app.application.ports.unit_of_work import UnitOfWorkFactory
from app.application.services.recommendation_engine import RecommendationEngine
from app.domain.comparison.exceptions import ComparisonNotFound
from app.domain.quotes.events import quote_event
from app.domain.recommendation.entities import Recommendation
from app.domain.recommendation.exceptions import RecommendationNotFound, RecommendationNotReady
from app.domain.recommendation.value_objects import RecommendationWeights


def _response(item: Recommendation) -> RecommendationResponse:
    return RecommendationResponse(
        id=item.id,
        comparison_id=item.comparison_id,
        tender_id=item.tender_id,
        recommendation_key=item.recommendation_key,
        policy_version=item.policy_version,
        weights=RecommendationWeightsResponse(
            technical=item.weights.technical,
            price=item.weights.price,
            delivery=item.weights.delivery,
        ),
        generated_by_user_id=item.generated_by_user_id,
        status=item.status,
        candidates=tuple(
            RecommendationCandidateResponse(
                supplier_id=candidate.supplier_id,
                supplier_name=candidate.supplier_name,
                eligible=candidate.eligible,
                product_count=candidate.product_count,
                technical_score=candidate.technical_score,
                price_score=candidate.price_score,
                delivery_score=candidate.delivery_score,
                score=candidate.score,
                exclusion_reasons=candidate.exclusion_reasons,
            )
            for candidate in item.candidates
        ),
        recommended_supplier_id=item.recommended_supplier_id,
        recommended_supplier_name=item.recommended_supplier_name,
        explanation=item.explanation,
        warnings=item.warnings,
        human_review_required=item.human_review_required,
        created_at=item.created_at,
    )


def _recommendation_key(
    comparison_id: UUID,
    comparison_key: str,
    policy_version: str,
    weights: RecommendationWeights,
) -> str:
    payload = "|".join(
        (
            str(comparison_id),
            comparison_key,
            policy_version.strip(),
            weights.canonical(),
        )
    )
    return hashlib.sha256(payload.encode()).hexdigest()


class GenerateRecommendation:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        engine: RecommendationEngine,
        *,
        policy_version: str,
    ) -> None:
        self._uow_factory = uow_factory
        self._engine = engine
        self._policy_version = policy_version

    def execute(
        self,
        comparison_id: UUID,
        generated_by_user_id: UUID,
        weights: RecommendationWeights,
    ) -> RecommendationResponse:
        with self._uow_factory() as uow:
            comparison = uow.comparisons.get(comparison_id)
            if comparison is None:
                raise ComparisonNotFound("Comparison was not found.")
            if not uow.users.exists(generated_by_user_id):
                raise RecommendationNotReady("Recommendation creator user does not exist.")
            key = _recommendation_key(
                comparison.id,
                comparison.comparison_key,
                self._policy_version,
                weights,
            )
            existing = uow.recommendations.get_by_key(comparison.id, key)
            if existing is not None:
                return _response(existing)

            recommendation = self._engine.build(
                comparison,
                weights,
                policy_version=self._policy_version,
                generated_by_user_id=generated_by_user_id,
                recommendation_key=key,
            )
            stored = uow.recommendations.create(recommendation)
            uow.audit_events.append(
                quote_event(
                    stored.id,
                    "recommendation.created",
                    aggregate_type="recommendation",
                    tender_id=str(stored.tender_id),
                    comparison_id=str(stored.comparison_id),
                    recommendation_key=stored.recommendation_key,
                    policy_version=stored.policy_version,
                    weights=stored.weights.as_dict(),
                    status=stored.status.value,
                    generated_by_user_id=str(stored.generated_by_user_id),
                )
            )
            uow.audit_events.append(
                quote_event(
                    stored.id,
                    f"recommendation.{stored.status.value}",
                    aggregate_type="recommendation",
                    tender_id=str(stored.tender_id),
                    comparison_id=str(stored.comparison_id),
                    recommended_supplier_id=(
                        str(stored.recommended_supplier_id)
                        if stored.recommended_supplier_id
                        else None
                    ),
                    eligible_supplier_count=sum(
                        1 for candidate in stored.candidates if candidate.eligible
                    ),
                    candidate_count=len(stored.candidates),
                    human_review_required=True,
                )
            )
            uow.commit()
            return _response(stored)


class GetLatestRecommendation:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, comparison_id: UUID) -> RecommendationResponse:
        with self._uow_factory() as uow:
            recommendation = uow.recommendations.get_latest(comparison_id)
            if recommendation is None:
                raise RecommendationNotFound("Recommendation was not found.")
            return _response(recommendation)


class GetRecommendation:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, recommendation_id: UUID) -> RecommendationResponse:
        with self._uow_factory() as uow:
            recommendation = uow.recommendations.get(recommendation_id)
            if recommendation is None:
                raise RecommendationNotFound("Recommendation was not found.")
            return _response(recommendation)
