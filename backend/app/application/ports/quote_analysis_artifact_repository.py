from abc import ABC, abstractmethod
from uuid import UUID

from app.domain.quotes.artifacts import ExtractionArtifact


class QuoteAnalysisArtifactRepository(ABC):
    @abstractmethod
    def create(self, artifact: ExtractionArtifact) -> ExtractionArtifact: ...

    @abstractmethod
    def get_by_run(self, extraction_run_id: UUID) -> ExtractionArtifact | None: ...

    @abstractmethod
    def list_by_quote(self, quote_id: UUID) -> list[ExtractionArtifact]: ...
