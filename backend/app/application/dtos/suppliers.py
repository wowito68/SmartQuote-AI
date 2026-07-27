from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from app.domain.suppliers.value_objects import (
    MergeSuggestionStatus,
    SupplierContactType,
    SupplierDiscoveryRunStatus,
    SupplierDiscoveryStage,
    SupplierStatus,
)


@dataclass(frozen=True, slots=True)
class SupplierDiscoveryRunResponse:
    id: UUID
    tender_id: UUID
    catalog_snapshot_id: UUID
    status: SupplierDiscoveryRunStatus
    current_stage: SupplierDiscoveryStage
    search_provider: str
    search_provider_version: str
    matching_algorithm_version: str
    reused: bool
    created_at: datetime


@dataclass(frozen=True, slots=True)
class SupplierDiscoveryRequestResponse:
    tender_id: UUID
    run: SupplierDiscoveryRunResponse
    queued: bool
    reused: bool


@dataclass(frozen=True, slots=True)
class SupplierContactResponse:
    id: UUID
    contact_type: SupplierContactType
    value: str
    confidence: float
    source_url: str
    contact_name: str | None
    role: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class SupplierSourceResponse:
    id: UUID
    provider_name: str
    source_type: str
    source_url: str
    source_title: str | None
    excerpt: str | None
    discovered_at: datetime


@dataclass(frozen=True, slots=True)
class ProductSupplierMatchResponse:
    id: UUID
    product_id: UUID
    score: float
    components: dict[str, float]
    reasons: tuple[str, ...]
    algorithm_version: str


@dataclass(frozen=True, slots=True)
class SupplierMergeSuggestionResponse:
    id: UUID
    source_supplier_id: UUID
    target_supplier_id: UUID
    score: float
    signals: tuple[str, ...]
    status: MergeSuggestionStatus


@dataclass(frozen=True, slots=True)
class TenderSupplierResponse:
    id: UUID
    tender_id: UUID
    supplier_id: UUID
    discovery_run_id: UUID | None
    status: SupplierStatus
    is_manual: bool
    legal_name: str | None
    trade_name: str | None
    website: str | None
    normalized_domain: str | None
    category: str | None
    country: str | None
    city: str | None
    description: str | None
    merged_into_supplier_id: UUID | None
    merged_into_tender_supplier_id: UUID | None
    reviewed_by_user_id: UUID | None
    reviewed_at: datetime | None
    rejection_reason: str | None
    contacts: tuple[SupplierContactResponse, ...]
    sources: tuple[SupplierSourceResponse, ...]
    matches: tuple[ProductSupplierMatchResponse, ...]
    merge_suggestions: tuple[SupplierMergeSuggestionResponse, ...]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class SupplierMetricsResponse:
    suppliers_total: int
    suppliers_pending_review: int
    suppliers_approved: int
    suppliers_rejected: int
    suppliers_merged: int
    duplicates_detected: int
    suppliers_with_valid_contact: int
    valid_contact_percentage: float
    approval_percentage: float
    average_search_duration_ms: float
    average_matching_duration_ms: float
    provider_error_count: int


@dataclass(frozen=True, slots=True)
class TenderSuppliersResponse:
    tender_id: UUID
    suppliers: tuple[TenderSupplierResponse, ...]
    discovery_runs: tuple[SupplierDiscoveryRunResponse, ...]
    metrics: SupplierMetricsResponse


@dataclass(frozen=True, slots=True)
class SupplierUpdateContact:
    contact_type: SupplierContactType
    value: str
    confidence: float
    source_url: str
    contact_name: str | None = None
    role: str | None = None


@dataclass(frozen=True, slots=True)
class SupplierUpdateCommand:
    changed_by_user_id: UUID
    legal_name: str | None = None
    trade_name: str | None = None
    website: str | None = None
    category: str | None = None
    country: str | None = None
    city: str | None = None
    description: str | None = None
    contacts: tuple[SupplierUpdateContact, ...] = ()


@dataclass(frozen=True, slots=True)
class ManualSupplierCommand:
    tender_id: UUID
    created_by_user_id: UUID
    legal_name: str | None
    trade_name: str | None
    website: str | None
    category: str | None
    country: str | None
    city: str | None
    description: str | None
    contacts: tuple[SupplierUpdateContact, ...] = ()
    source_note: str | None = None


@dataclass(frozen=True, slots=True)
class SupplierDiscoveryExampleMetrics:
    suppliers_found: int
    duplicates_detected: int
    contacts_found: int
    search_duration_ms: int | None
    matching_duration_ms: int | None
    provider_errors: tuple[str, ...]
    metadata: dict[str, Any]
