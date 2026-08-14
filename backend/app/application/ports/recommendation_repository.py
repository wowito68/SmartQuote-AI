from abc import ABC, abstractmethod
from uuid import UUID

from app.domain.recommendation.entities import Recommendation


class RecommendationRepository(ABC):
    @abstractmethod
    def create(self, recommendation: Recommendation) -> Recommendation:
        raise NotImplementedError

    @abstractmethod
    def get(self, recommendation_id: UUID) -> Recommendation | None:
        raise NotImplementedError

    @abstractmethod
    def get_by_key(
        self,
        comparison_id: UUID,
        recommendation_key: str,
    ) -> Recommendation | None:
        raise NotImplementedError

    @abstractmethod
    def get_latest(self, comparison_id: UUID) -> Recommendation | None:
        raise NotImplementedError
