from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.infrastructure.db.base import Base


class RecommendationModel(Base):
    __tablename__ = "recommendations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('ready', 'withheld')",
            name="valid_recommendation_status",
        ),
        CheckConstraint(
            "human_review_required = true",
            name="recommendation_requires_human_review",
        ),
        UniqueConstraint(
            "comparison_id",
            "recommendation_key",
            name="uq_recommendations_comparison_key",
        ),
        Index("ix_recommendations_comparison_id", "comparison_id"),
        Index("ix_recommendations_tender_id", "tender_id"),
        Index("ix_recommendations_status", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    comparison_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("comparisons.id", ondelete="RESTRICT"),
        nullable=False,
    )
    tender_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("tenders.id", ondelete="CASCADE"),
        nullable=False,
    )
    recommendation_key: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(50), nullable=False)
    weights: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False)
    generated_by_user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    candidates: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    recommended_supplier_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("suppliers.id", ondelete="SET NULL"),
        nullable=True,
    )
    recommended_supplier_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    warnings: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    human_review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
