from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from app.domain.shared.exceptions import ValidationError


@dataclass(frozen=True, slots=True)
class ComparisonRun:
    tender_id: UUID
    catalog_snapshot_id: UUID
    comparison_key: str
    approved_quotes_version: str
    scoring_config_version: str
    rows: tuple[dict[str, Any], ...]
    recommendation: dict[str, Any]
    generated_by_user_id: UUID
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if len(self.comparison_key) != 64:
            raise ValidationError("Comparison key must be a SHA-256 digest.")
        if not self.approved_quotes_version.strip() or not self.scoring_config_version.strip():
            raise ValidationError("Comparison version metadata is required.")
        if not self.rows:
            raise ValidationError("Comparison must contain at least one row.")
        if self.recommendation.get("human_review_required") is not True:
            raise ValidationError("Recommendation must explicitly require human review.")
