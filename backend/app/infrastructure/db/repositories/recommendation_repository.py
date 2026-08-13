from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.ports.recommendation_repository import RecommendationRepository
from app.domain.recommendation.entities import Recommendation, RecommendationCandidate
from app.domain.recommendation.value_objects import RecommendationStatus, RecommendationWeights
from app.infrastructure.db.models.recommendation import RecommendationModel


def _candidate_to_dict(candidate: RecommendationCandidate) -> dict:
    return {
        "supplier_id": str(candidate.supplier_id),
        "supplier_name": candidate.supplier_name,
        "eligible": candidate.eligible,
        "product_count": candidate.product_count,
        "technical_score": (
            str(candidate.technical_score) if candidate.technical_score is not None else None
        ),
        "price_score": str(candidate.price_score) if candidate.price_score is not None else None,
        "delivery_score": (
            str(candidate.delivery_score) if candidate.delivery_score is not None else None
        ),
        "score": str(candidate.score) if candidate.score is not None else None,
        "exclusion_reasons": list(candidate.exclusion_reasons),
    }


def _candidate_from_dict(payload: dict) -> RecommendationCandidate:
    def decimal(name: str) -> Decimal | None:
        value = payload.get(name)
        return Decimal(str(value)) if value is not None else None

    return RecommendationCandidate(
        supplier_id=UUID(str(payload["supplier_id"])),
        supplier_name=str(payload["supplier_name"]),
        eligible=bool(payload["eligible"]),
        product_count=int(payload["product_count"]),
        technical_score=decimal("technical_score"),
        price_score=decimal("price_score"),
        delivery_score=decimal("delivery_score"),
        score=decimal("score"),
        exclusion_reasons=tuple(str(value) for value in payload.get("exclusion_reasons", [])),
    )


class SqlAlchemyRecommendationRepository(RecommendationRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, recommendation: Recommendation) -> Recommendation:
        self._session.add(
            RecommendationModel(
                id=recommendation.id,
                comparison_id=recommendation.comparison_id,
                tender_id=recommendation.tender_id,
                recommendation_key=recommendation.recommendation_key,
                policy_version=recommendation.policy_version,
                weights=recommendation.weights.as_dict(),
                generated_by_user_id=recommendation.generated_by_user_id,
                status=recommendation.status.value,
                candidates=[_candidate_to_dict(value) for value in recommendation.candidates],
                recommended_supplier_id=recommendation.recommended_supplier_id,
                recommended_supplier_name=recommendation.recommended_supplier_name,
                explanation=recommendation.explanation,
                warnings=list(recommendation.warnings),
                human_review_required=recommendation.human_review_required,
                created_at=recommendation.created_at,
            )
        )
        self._session.flush()
        return self.get(recommendation.id) or recommendation

    def get(self, recommendation_id: UUID) -> Recommendation | None:
        model = self._session.get(RecommendationModel, recommendation_id)
        return self._hydrate(model) if model else None

    def get_by_key(
        self,
        comparison_id: UUID,
        recommendation_key: str,
    ) -> Recommendation | None:
        model = self._session.scalars(
            select(RecommendationModel).where(
                RecommendationModel.comparison_id == comparison_id,
                RecommendationModel.recommendation_key == recommendation_key,
            )
        ).first()
        return self._hydrate(model) if model else None

    def get_latest(self, comparison_id: UUID) -> Recommendation | None:
        model = self._session.scalars(
            select(RecommendationModel)
            .where(RecommendationModel.comparison_id == comparison_id)
            .order_by(RecommendationModel.created_at.desc(), RecommendationModel.id.desc())
        ).first()
        return self._hydrate(model) if model else None

    @staticmethod
    def _hydrate(model: RecommendationModel) -> Recommendation:
        return Recommendation(
            id=model.id,
            comparison_id=model.comparison_id,
            tender_id=model.tender_id,
            recommendation_key=model.recommendation_key,
            policy_version=model.policy_version,
            weights=RecommendationWeights(
                technical=Decimal(model.weights["technical"]),
                price=Decimal(model.weights["price"]),
                delivery=Decimal(model.weights["delivery"]),
            ),
            generated_by_user_id=model.generated_by_user_id,
            status=RecommendationStatus(model.status),
            candidates=tuple(_candidate_from_dict(value) for value in model.candidates),
            recommended_supplier_id=model.recommended_supplier_id,
            recommended_supplier_name=model.recommended_supplier_name,
            explanation=model.explanation,
            warnings=tuple(str(value) for value in model.warnings),
            human_review_required=model.human_review_required,
            created_at=model.created_at,
        )
