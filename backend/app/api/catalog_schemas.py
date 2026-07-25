from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.catalog.value_objects import AIExtractionRunStatus, ProductStatus


class CatalogExtractionRunResponseSchema(BaseModel):
    id: UUID
    document_id: UUID
    status: AIExtractionRunStatus
    prompt_version: str
    model: str
    reused: bool

    model_config = ConfigDict(from_attributes=True)


class CatalogExtractionRequestResponseSchema(BaseModel):
    tender_id: UUID
    runs: list[CatalogExtractionRunResponseSchema]
    queued: int = Field(ge=0)
    reused: int = Field(ge=0)


class EvidenceReferenceResponseSchema(BaseModel):
    document_id: UUID
    page_number: int = Field(ge=1)
    text_fragment: str
    confidence: float = Field(ge=0, le=1)
    x0: float | None
    y0: float | None
    x1: float | None
    y1: float | None
    model: str
    prompt_version: str

    model_config = ConfigDict(from_attributes=True)


class CatalogProductResponseSchema(BaseModel):
    id: UUID
    tender_id: UUID
    source_document_id: UUID
    ai_extraction_run_id: UUID
    item_number: str | None
    name: str
    description: str | None
    quantity: Decimal | None
    unit: str | None
    category: str | None
    specifications: dict[str, str]
    observations: str | None
    confidence: float = Field(ge=0, le=1)
    status: ProductStatus
    duplicate_of_product_id: UUID | None
    manual_edit_count: int = Field(ge=0)
    reviewed_by_user_id: UUID | None
    reviewed_at: datetime | None
    rejection_reason: str | None
    original_payload: dict[str, Any]
    evidence: list[EvidenceReferenceResponseSchema]

    model_config = ConfigDict(from_attributes=True)


class CatalogMetricsResponseSchema(BaseModel):
    products_total: int = Field(ge=0)
    products_pending_review: int = Field(ge=0)
    products_approved: int = Field(ge=0)
    products_rejected: int = Field(ge=0)
    average_confidence: float = Field(ge=0, le=1)
    manual_edit_percentage: float = Field(ge=0, le=100)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    estimated_cost_usd: Decimal = Field(ge=0)

    model_config = ConfigDict(from_attributes=True)


class TenderCatalogResponseSchema(BaseModel):
    tender_id: UUID
    products: list[CatalogProductResponseSchema]
    metrics: CatalogMetricsResponseSchema
    latest_snapshot_id: UUID | None
    latest_snapshot_version: int | None


class CatalogProductUpdateRequestSchema(BaseModel):
    action: Literal["edit", "approve", "reject"]
    reviewer_user_id: UUID
    name: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = None
    quantity: Decimal | None = Field(default=None, gt=0)
    unit: str | None = Field(default=None, max_length=100)
    category: str | None = Field(default=None, max_length=255)
    specifications: dict[str, str] | None = None
    observations: str | None = None
    rejection_reason: str | None = Field(default=None, max_length=2000)


class CatalogApprovalRequestSchema(BaseModel):
    approved_by_user_id: UUID


class CatalogSnapshotResponseSchema(BaseModel):
    id: UUID
    tender_id: UUID
    version: int = Field(ge=1)
    approved_by_user_id: UUID
    products: list[dict[str, Any]]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
