from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.suppliers.value_objects import (
    MergeSuggestionStatus,
    SupplierContactType,
    SupplierDiscoveryRunStatus,
    SupplierDiscoveryStage,
    SupplierStatus,
)


class SupplierDiscoveryRequestSchema(BaseModel):
    requested_by_user_id: UUID


class SupplierDiscoveryRunResponseSchema(BaseModel):
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

    model_config = ConfigDict(from_attributes=True)


class SupplierDiscoveryRequestResponseSchema(BaseModel):
    tender_id: UUID
    run: SupplierDiscoveryRunResponseSchema
    queued: bool
    reused: bool

    model_config = ConfigDict(from_attributes=True)


class SupplierContactInputSchema(BaseModel):
    contact_type: SupplierContactType
    value: str = Field(min_length=1, max_length=2000)
    confidence: float = Field(ge=0, le=1)
    source_url: str = Field(min_length=1, max_length=2000)
    contact_name: str | None = Field(default=None, max_length=255)
    role: str | None = Field(default=None, max_length=255)


class SupplierContactResponseSchema(BaseModel):
    id: UUID
    contact_type: SupplierContactType
    value: str
    confidence: float = Field(ge=0, le=1)
    source_url: str
    contact_name: str | None
    role: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SupplierSourceResponseSchema(BaseModel):
    id: UUID
    provider_name: str
    source_type: str
    source_url: str
    source_title: str | None
    excerpt: str | None
    discovered_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProductSupplierMatchResponseSchema(BaseModel):
    id: UUID
    product_id: UUID
    score: float = Field(ge=0, le=100)
    components: dict[str, float]
    reasons: tuple[str, ...]
    algorithm_version: str

    model_config = ConfigDict(from_attributes=True)


class SupplierMergeSuggestionResponseSchema(BaseModel):
    id: UUID
    source_supplier_id: UUID
    target_supplier_id: UUID
    score: float = Field(ge=0, le=1)
    signals: tuple[str, ...]
    status: MergeSuggestionStatus

    model_config = ConfigDict(from_attributes=True)


class TenderSupplierResponseSchema(BaseModel):
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
    contacts: tuple[SupplierContactResponseSchema, ...]
    sources: tuple[SupplierSourceResponseSchema, ...]
    matches: tuple[ProductSupplierMatchResponseSchema, ...]
    merge_suggestions: tuple[SupplierMergeSuggestionResponseSchema, ...]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SupplierMetricsResponseSchema(BaseModel):
    suppliers_total: int = Field(ge=0)
    suppliers_pending_review: int = Field(ge=0)
    suppliers_approved: int = Field(ge=0)
    suppliers_rejected: int = Field(ge=0)
    suppliers_merged: int = Field(ge=0)
    duplicates_detected: int = Field(ge=0)
    suppliers_with_valid_contact: int = Field(ge=0)
    valid_contact_percentage: float = Field(ge=0, le=100)
    approval_percentage: float = Field(ge=0, le=100)
    average_search_duration_ms: float = Field(ge=0)
    average_matching_duration_ms: float = Field(ge=0)
    provider_error_count: int = Field(ge=0)

    model_config = ConfigDict(from_attributes=True)


class TenderSuppliersResponseSchema(BaseModel):
    tender_id: UUID
    suppliers: tuple[TenderSupplierResponseSchema, ...]
    discovery_runs: tuple[SupplierDiscoveryRunResponseSchema, ...]
    metrics: SupplierMetricsResponseSchema

    model_config = ConfigDict(from_attributes=True)


class SupplierUpdateRequestSchema(BaseModel):
    changed_by_user_id: UUID
    legal_name: str | None = Field(default=None, max_length=500)
    trade_name: str | None = Field(default=None, max_length=500)
    website: str | None = Field(default=None, max_length=2000)
    category: str | None = Field(default=None, max_length=255)
    country: str | None = Field(default=None, max_length=100)
    city: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    contacts: tuple[SupplierContactInputSchema, ...] = ()


class SupplierApprovalRequestSchema(BaseModel):
    reviewer_user_id: UUID


class SupplierRejectionRequestSchema(BaseModel):
    reviewer_user_id: UUID
    reason: str = Field(min_length=1, max_length=2000)


class SupplierMergeRequestSchema(BaseModel):
    source_tender_supplier_id: UUID
    target_tender_supplier_id: UUID
    reviewer_user_id: UUID
    suggestion_id: UUID | None = None

    @model_validator(mode="after")
    def validate_distinct_suppliers(self) -> "SupplierMergeRequestSchema":
        if self.source_tender_supplier_id == self.target_tender_supplier_id:
            raise ValueError("Source and target suppliers must be different.")
        return self


class ManualSupplierRequestSchema(BaseModel):
    tender_id: UUID
    created_by_user_id: UUID
    legal_name: str | None = Field(default=None, max_length=500)
    trade_name: str | None = Field(default=None, max_length=500)
    website: str | None = Field(default=None, max_length=2000)
    category: str | None = Field(default=None, max_length=255)
    country: str | None = Field(default=None, max_length=100)
    city: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    contacts: tuple[SupplierContactInputSchema, ...] = ()
    source_note: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def validate_name(self) -> "ManualSupplierRequestSchema":
        if not (self.legal_name and self.legal_name.strip()) and not (
            self.trade_name and self.trade_name.strip()
        ):
            raise ValueError("Legal name or trade name is required.")
        return self
