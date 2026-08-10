from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.ports.quote_analysis_artifact_repository import (
    QuoteAnalysisArtifactRepository,
)
from app.domain.quotes.artifacts import ExtractionArtifact
from app.infrastructure.db.models.quote import QuoteExtractionRunModel
from app.infrastructure.db.models.quote_analysis import QuoteExtractionArtifactModel


def _from_model(model: QuoteExtractionArtifactModel) -> ExtractionArtifact:
    return ExtractionArtifact(
        id=model.id,
        extraction_run_id=model.extraction_run_id,
        schema_version=model.schema_version,
        structured_output=dict(model.structured_output or {}),
        created_at=model.created_at,
    )


class SqlAlchemyQuoteAnalysisArtifactRepository(QuoteAnalysisArtifactRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, artifact: ExtractionArtifact) -> ExtractionArtifact:
        existing = self._session.scalars(
            select(QuoteExtractionArtifactModel).where(
                QuoteExtractionArtifactModel.extraction_run_id
                == artifact.extraction_run_id
            )
        ).first()
        if existing is not None:
            return _from_model(existing)
        model = QuoteExtractionArtifactModel(
            id=artifact.id,
            extraction_run_id=artifact.extraction_run_id,
            schema_version=artifact.schema_version,
            structured_output=artifact.structured_output,
            created_at=artifact.created_at,
        )
        self._session.add(model)
        self._session.flush()
        return _from_model(model)

    def get_by_run(self, extraction_run_id: UUID) -> ExtractionArtifact | None:
        model = self._session.scalars(
            select(QuoteExtractionArtifactModel).where(
                QuoteExtractionArtifactModel.extraction_run_id == extraction_run_id
            )
        ).first()
        return _from_model(model) if model else None

    def list_by_quote(self, quote_id: UUID) -> list[ExtractionArtifact]:
        statement = (
            select(QuoteExtractionArtifactModel)
            .join(
                QuoteExtractionRunModel,
                QuoteExtractionRunModel.id
                == QuoteExtractionArtifactModel.extraction_run_id,
            )
            .where(QuoteExtractionRunModel.quote_id == quote_id)
            .order_by(
                QuoteExtractionArtifactModel.created_at,
                QuoteExtractionArtifactModel.id,
            )
        )
        return [_from_model(model) for model in self._session.scalars(statement)]
