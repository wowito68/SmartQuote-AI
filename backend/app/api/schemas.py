from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.tenders.entities import DESCRIPTION_MAX_LENGTH, TITLE_MAX_LENGTH
from app.domain.tenders.value_objects import TenderStatus


class CreateTenderRequestSchema(BaseModel):
    title: str = Field(min_length=1, max_length=TITLE_MAX_LENGTH)
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX_LENGTH)
    deadline: datetime | None = None
    created_by_user_id: UUID

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("title must not be blank")
        return value.strip()

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    @field_validator("deadline")
    @classmethod
    def deadline_must_include_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("deadline must include a timezone")
        return value

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "title": "Adquisición de transformadores 2026",
                "description": "Licitación para suministro nacional.",
                "deadline": "2026-08-31T18:00:00-06:00",
                "created_by_user_id": "00000000-0000-0000-0000-000000000001",
            }
        }
    )


class UpdateTenderRequestSchema(BaseModel):
    title: str = Field(min_length=1, max_length=TITLE_MAX_LENGTH)
    description: str | None = Field(max_length=DESCRIPTION_MAX_LENGTH)
    deadline: datetime | None
    status: TenderStatus

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("title must not be blank")
        return value.strip()

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    @field_validator("deadline")
    @classmethod
    def deadline_must_include_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("deadline must include a timezone")
        return value


class TenderResponseSchema(BaseModel):
    id: UUID
    title: str
    description: str | None
    status: TenderStatus
    deadline: datetime | None
    created_by_user_id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TenderListResponseSchema(BaseModel):
    items: list[TenderResponseSchema]
    total: int = Field(ge=0)


class ErrorResponseSchema(BaseModel):
    code: str
    message: str
    details: list[dict[str, Any]] | None = None
