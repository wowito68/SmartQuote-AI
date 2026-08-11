from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from app.domain.shared.exceptions import ValidationError


@dataclass(frozen=True, slots=True)
class ExtractionArtifact:
    extraction_run_id: UUID
    schema_version: str
    structured_output: dict[str, Any]
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        schema_version = self.schema_version.strip()
        if not schema_version:
            raise ValidationError("Extraction artifact schema version is required.")
        if not isinstance(self.structured_output, dict):
            raise ValidationError("Extraction artifact output must be an object.")
        object.__setattr__(self, "schema_version", schema_version)
        object.__setattr__(self, "structured_output", dict(self.structured_output))
