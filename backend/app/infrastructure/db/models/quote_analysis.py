from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.infrastructure.db.base import Base


class QuoteExtractionArtifactModel(Base):
    __tablename__ = "quote_extraction_artifacts"
    __table_args__ = (
        UniqueConstraint(
            "extraction_run_id",
            name="uq_quote_extraction_artifacts_run",
        ),
        Index("ix_quote_extraction_artifacts_run", "extraction_run_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    extraction_run_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("quote_extraction_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    schema_version: Mapped[str] = mapped_column(String(50), nullable=False)
    structured_output: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
