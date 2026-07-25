from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.domain.catalog.value_objects import AIExtractionRunStatus, ProductStatus


@dataclass(frozen=True, slots=True)
class CatalogExtractionRunResponse:
    id: UUID
    document_id: UUID
    status: AIExtractionRunStatus
    prompt_version: str
    model: str
    reused: bool


@dataclass(frozen=True, slots=True)
class CatalogExtractionRequestResponse:
    tender_id: UUID
    runs: tuple[CatalogExtractionRunResponse, ...]
    queued: int
    reused: int


@dataclass(frozen=True, slots=True)
class EvidenceReferenceResponse:
    document_id: UUID
    page_number: int
    text_fragment: str
    confidence: float
    x0: float | None
    y0: float | None
    x1: float | None
    y1: float | None
    model: str
    prompt_version: str


@dataclass(frozen=True, slots=True)
class CatalogProductResponse:
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
    confidence: float
    status: ProductStatus
    duplicate_of_product_id: UUID | None
    manual_edit_count: int
    reviewed_by_user_id: UUID | None
    reviewed_at: datetime | None
    rejection_reason: str | None
    original_payload: dict[str, Any]
    evidence: tuple[EvidenceReferenceResponse, ...] = ()


@dataclass(frozen=True, slots=True)
class CatalogMetricsResponse:
    products_total: int
    products_pending_review: int
    products_approved: int
    products_rejected: int
    average_confidence: float
    manual_edit_percentage: float
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: Decimal


@dataclass(frozen=True, slots=True)
class TenderCatalogResponse:
    tender_id: UUID
    products: tuple[CatalogProductResponse, ...]
    metrics: CatalogMetricsResponse
    latest_snapshot_id: UUID | None
    latest_snapshot_version: int | None


@dataclass(frozen=True, slots=True)
class CatalogSnapshotResponse:
    id: UUID
    tender_id: UUID
    version: int
    approved_by_user_id: UUID
    products: tuple[dict[str, Any], ...]
    created_at: datetime
