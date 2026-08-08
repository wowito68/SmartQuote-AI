from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from app.domain.suppliers.value_objects import (
    SupplierDiscoveryRunStatus,
    SupplierDiscoveryStage,
    SupplierMatchStatus,
    SupplierStatus,
)


@dataclass(frozen=True, slots=True)
class SupplierDiscoveryRunTraceResponse:
    id: UUID
    tender_id: UUID
    catalog_snapshot_id: UUID
    status: SupplierDiscoveryRunStatus
    current_stage: SupplierDiscoveryStage
    search_provider: str
    search_provider_version: str
    matching_algorithm_version: str
    query_version: str
    search_identity_key: str
    correlation_id: str
    refresh_sequence: int
    refresh_of_run_id: UUID | None
    estimated_cost_usd: float
    reused: bool
    created_at: datetime


@dataclass(frozen=True, slots=True)
class SupplierDiscoveryRequestTraceResponse:
    tender_id: UUID
    run: SupplierDiscoveryRunTraceResponse
    queued: bool
    reused: bool


@dataclass(frozen=True, slots=True)
class SupplierCandidateTraceResponse:
    run_id: UUID
    product_id: UUID
    supplier_id: UUID
    tender_supplier_id: UUID
    status: SupplierStatus
    legal_name: str | None
    trade_name: str | None
    website: str | None
    normalized: dict[str, Any]
    source_url: str
    source_title: str | None
    source_type: str
    query: str
    search_provider: str
    searched_at: datetime | None
    initial_score: float | None
    duplicate_status: str
    duplicate_score: float
    duplicate_signals: tuple[str, ...]
    match_score: float | None
    match_status: SupplierMatchStatus | None
    match_reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SupplierCandidatesResponse:
    tender_id: UUID
    candidates: tuple[SupplierCandidateTraceResponse, ...]


@dataclass(frozen=True, slots=True)
class ProductSupplierTraceResponse:
    product_id: UUID
    tender_supplier_id: UUID
    supplier_id: UUID
    status: SupplierStatus
    legal_name: str | None
    trade_name: str | None
    website: str | None
    match_score: float
    match_status: SupplierMatchStatus
    source_url: str | None
    reason: str
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProductSuppliersResponse:
    product_id: UUID
    suppliers: tuple[ProductSupplierTraceResponse, ...]
