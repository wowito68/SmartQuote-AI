from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError as PydanticValidationError

from app.domain.catalog.exceptions import AIResponseValidationError


class CoordinatePayload(BaseModel):
    x0: float = Field(ge=0)
    y0: float = Field(ge=0)
    x1: float = Field(ge=0)
    y1: float = Field(ge=0)

    model_config = ConfigDict(extra="forbid")


class EvidencePayload(BaseModel):
    page: int = Field(ge=1)
    fragment: str = Field(min_length=1, max_length=4000)
    confidence: float = Field(ge=0, le=1)
    coordinates: CoordinatePayload | None

    model_config = ConfigDict(extra="forbid")


class SpecificationPayload(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    value: str = Field(min_length=1, max_length=2000)

    model_config = ConfigDict(extra="forbid")


class ProductPayload(BaseModel):
    item_number: str | None
    name: str = Field(min_length=1, max_length=500)
    description: str | None
    quantity: Decimal | None = Field(default=None, gt=0)
    unit: str | None
    suggested_category: str | None
    technical_specifications: list[SpecificationPayload]
    observations: str | None
    confidence: float = Field(ge=0, le=1)
    evidence: list[EvidencePayload] = Field(min_length=1)

    model_config = ConfigDict(extra="forbid")


class CatalogExtractionPayload(BaseModel):
    products: list[ProductPayload]

    model_config = ConfigDict(extra="forbid")


def validate_ai_payload(payload: dict[str, Any]) -> CatalogExtractionPayload:
    try:
        return CatalogExtractionPayload.model_validate(payload)
    except PydanticValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors()
        )
        raise AIResponseValidationError(f"AI JSON failed validation: {details}") from exc
