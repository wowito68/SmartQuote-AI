from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse
from uuid import UUID, uuid4

from app.domain.shared.exceptions import ValidationError
from app.domain.suppliers.exceptions import (
    InvalidSupplierDiscoveryState,
    InvalidSupplierState,
    SupplierMergeConflict,
)
from app.domain.suppliers.value_objects import (
    MergeSuggestionStatus,
    SupplierConfidence,
    SupplierContactType,
    SupplierDiscoveryRunStatus,
    SupplierDiscoveryStage,
    SupplierMatchScore,
    SupplierStatus,
)


def _now() -> datetime:
    return datetime.now(UTC)


def _clean(value: str | None, *, limit: int | None = None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.split())
    if not cleaned:
        return None
    return cleaned[:limit] if limit else cleaned


def _website_domain(website: str | None) -> str | None:
    if website is None:
        return None
    candidate = website.strip()
    if not candidate:
        return None
    parsed = urlparse(candidate if "://" in candidate else f"https://{candidate}")
    host = (parsed.hostname or "").lower().strip(".")
    if host.startswith("www."):
        host = host[4:]
    return host or None


_SUPPLIER_TRANSITIONS = {
    SupplierStatus.CANDIDATE: {SupplierStatus.CONTACTS_FOUND},
    SupplierStatus.CONTACTS_FOUND: {SupplierStatus.PENDING_REVIEW},
    SupplierStatus.PENDING_REVIEW: {
        SupplierStatus.APPROVED,
        SupplierStatus.REJECTED,
        SupplierStatus.MERGED,
    },
    SupplierStatus.APPROVED: {SupplierStatus.MERGED},
    SupplierStatus.REJECTED: set(),
    SupplierStatus.MERGED: set(),
}


@dataclass(slots=True)
class Supplier:
    legal_name: str | None = None
    trade_name: str | None = None
    website: str | None = None
    category: str | None = None
    country: str | None = None
    city: str | None = None
    description: str | None = None
    id: UUID = field(default_factory=uuid4)
    normalized_domain: str | None = None
    merged_into_supplier_id: UUID | None = None
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)

    def __post_init__(self) -> None:
        self.legal_name = _clean(self.legal_name, limit=500)
        self.trade_name = _clean(self.trade_name, limit=500)
        if not self.legal_name and not self.trade_name:
            raise ValidationError("Supplier legal name or trade name is required.")
        self.website = _clean(self.website, limit=2000)
        self.normalized_domain = _website_domain(self.website)
        self.category = _clean(self.category, limit=255)
        self.country = _clean(self.country, limit=100)
        self.city = _clean(self.city, limit=255)
        self.description = _clean(self.description, limit=5000)

    @property
    def display_name(self) -> str:
        return self.trade_name or self.legal_name or "Unnamed supplier"

    def edit(
        self,
        *,
        legal_name: str | None = None,
        trade_name: str | None = None,
        website: str | None = None,
        category: str | None = None,
        country: str | None = None,
        city: str | None = None,
        description: str | None = None,
    ) -> None:
        if self.merged_into_supplier_id is not None:
            raise InvalidSupplierState("Merged suppliers cannot be edited.")
        if legal_name is not None:
            self.legal_name = _clean(legal_name, limit=500)
        if trade_name is not None:
            self.trade_name = _clean(trade_name, limit=500)
        if not self.legal_name and not self.trade_name:
            raise ValidationError("Supplier legal name or trade name is required.")
        if website is not None:
            self.website = _clean(website, limit=2000)
            self.normalized_domain = _website_domain(self.website)
        if category is not None:
            self.category = _clean(category, limit=255)
        if country is not None:
            self.country = _clean(country, limit=100)
        if city is not None:
            self.city = _clean(city, limit=255)
        if description is not None:
            self.description = _clean(description, limit=5000)
        self.updated_at = _now()

    def merge_into(self, target_supplier_id: UUID) -> None:
        if target_supplier_id == self.id:
            raise SupplierMergeConflict("A supplier cannot be merged into itself.")
        if self.merged_into_supplier_id is not None:
            raise SupplierMergeConflict("Supplier has already been merged.")
        self.merged_into_supplier_id = target_supplier_id
        self.updated_at = _now()


@dataclass(frozen=True, slots=True)
class SupplierContact:
    supplier_id: UUID
    contact_type: SupplierContactType
    value: str
    confidence: SupplierConfidence
    source_url: str
    contact_name: str | None = None
    role: str | None = None
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=_now)

    def __post_init__(self) -> None:
        value = _clean(self.value, limit=2000)
        source_url = _clean(self.source_url, limit=2000)
        if not value:
            raise ValidationError("Supplier contact value is required.")
        if not source_url:
            raise ValidationError("Supplier contact source is required.")
        if self.contact_type is SupplierContactType.EMAIL and (
            "@" not in value or value.startswith("@") or value.endswith("@")
        ):
            raise ValidationError("Supplier email is invalid.")
        if self.contact_type in {SupplierContactType.PHONE, SupplierContactType.WHATSAPP}:
            digits = "".join(character for character in value if character.isdigit())
            if len(digits) < 7:
                raise ValidationError("Supplier phone contact is invalid.")
        if self.contact_type is SupplierContactType.CONTACT_FORM:
            parsed = urlparse(value)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValidationError("Supplier contact form URL is invalid.")
        object.__setattr__(self, "value", value)
        object.__setattr__(self, "source_url", source_url)
        object.__setattr__(self, "contact_name", _clean(self.contact_name, limit=255))
        object.__setattr__(self, "role", _clean(self.role, limit=255))

    @property
    def identity_key(self) -> str:
        if self.contact_type is SupplierContactType.EMAIL:
            normalized = self.value.casefold()
        elif self.contact_type in {SupplierContactType.PHONE, SupplierContactType.WHATSAPP}:
            normalized = "".join(character for character in self.value if character.isdigit())
        else:
            normalized = self.value.rstrip("/").casefold()
        return f"{self.contact_type.value}:{normalized}"


@dataclass(frozen=True, slots=True)
class SupplierSource:
    supplier_id: UUID
    provider_name: str
    source_type: str
    source_url: str
    source_title: str | None = None
    excerpt: str | None = None
    id: UUID = field(default_factory=uuid4)
    discovered_at: datetime = field(default_factory=_now)

    def __post_init__(self) -> None:
        provider = _clean(self.provider_name, limit=255)
        source_type = _clean(self.source_type, limit=100)
        source_url = _clean(self.source_url, limit=2000)
        if not provider or not source_type or not source_url:
            raise ValidationError("Supplier source provider, type and URL are required.")
        object.__setattr__(self, "provider_name", provider)
        object.__setattr__(self, "source_type", source_type)
        object.__setattr__(self, "source_url", source_url)
        object.__setattr__(self, "source_title", _clean(self.source_title, limit=500))
        object.__setattr__(self, "excerpt", _clean(self.excerpt, limit=4000))


@dataclass(slots=True)
class TenderSupplier:
    tender_id: UUID
    supplier_id: UUID
    discovery_run_id: UUID | None = None
    status: SupplierStatus = SupplierStatus.CANDIDATE
    is_manual: bool = False
    id: UUID = field(default_factory=uuid4)
    reviewed_by_user_id: UUID | None = None
    reviewed_at: datetime | None = None
    rejection_reason: str | None = None
    merged_into_tender_supplier_id: UUID | None = None
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)

    def _transition(self, target: SupplierStatus) -> None:
        if target is self.status:
            return
        if target not in _SUPPLIER_TRANSITIONS[self.status]:
            raise InvalidSupplierState(
                f"Supplier cannot transition from {self.status.value} to {target.value}."
            )
        self.status = target
        self.updated_at = _now()

    def mark_contact_discovery_complete(self) -> None:
        self._transition(SupplierStatus.CONTACTS_FOUND)

    def start_review(self) -> None:
        self._transition(SupplierStatus.PENDING_REVIEW)

    def approve(self, reviewer_user_id: UUID) -> None:
        self._transition(SupplierStatus.APPROVED)
        self.reviewed_by_user_id = reviewer_user_id
        self.reviewed_at = self.updated_at
        self.rejection_reason = None

    def reject(self, reviewer_user_id: UUID, reason: str) -> None:
        cleaned = _clean(reason, limit=2000)
        if not cleaned:
            raise ValidationError("A supplier rejection reason is required.")
        self._transition(SupplierStatus.REJECTED)
        self.reviewed_by_user_id = reviewer_user_id
        self.reviewed_at = self.updated_at
        self.rejection_reason = cleaned

    def merge_into(self, target_tender_supplier_id: UUID, reviewer_user_id: UUID) -> None:
        if target_tender_supplier_id == self.id:
            raise SupplierMergeConflict("A tender supplier cannot be merged into itself.")
        self._transition(SupplierStatus.MERGED)
        self.merged_into_tender_supplier_id = target_tender_supplier_id
        self.reviewed_by_user_id = reviewer_user_id
        self.reviewed_at = self.updated_at


@dataclass(slots=True)
class SupplierDiscoveryRun:
    tender_id: UUID
    catalog_snapshot_id: UUID
    requested_by_user_id: UUID
    idempotency_key: str
    search_provider: str
    search_provider_version: str
    search_configuration: dict[str, Any]
    matching_algorithm_version: str
    id: UUID = field(default_factory=uuid4)
    status: SupplierDiscoveryRunStatus = SupplierDiscoveryRunStatus.QUEUED
    current_stage: SupplierDiscoveryStage = SupplierDiscoveryStage.QUEUED
    raw_candidates: list[dict[str, Any]] = field(default_factory=list)
    processed_candidates: list[dict[str, Any]] = field(default_factory=list)
    suppliers_found: int = 0
    duplicates_detected: int = 0
    contacts_found: int = 0
    provider_errors: list[str] = field(default_factory=list)
    search_duration_ms: int | None = None
    matching_duration_ms: int | None = None
    error_type: str | None = None
    error_message: str | None = None
    reused_from_run_id: UUID | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime = field(default_factory=_now)

    def __post_init__(self) -> None:
        if len(self.idempotency_key) != 64:
            raise ValidationError("Supplier discovery idempotency key must be SHA-256.")
        if not _clean(self.search_provider) or not _clean(self.search_provider_version):
            raise ValidationError("Supplier search provider and version are required.")
        if not _clean(self.matching_algorithm_version):
            raise ValidationError("Supplier matching algorithm version is required.")

    def start(self) -> None:
        if self.status in {
            SupplierDiscoveryRunStatus.COMPLETED,
            SupplierDiscoveryRunStatus.REUSED,
        }:
            return
        self.status = SupplierDiscoveryRunStatus.RUNNING
        self.current_stage = SupplierDiscoveryStage.SEARCH
        self.started_at = self.started_at or _now()
        self.completed_at = None
        self.error_type = None
        self.error_message = None

    def save_search_results(
        self,
        candidates: list[dict[str, Any]],
        *,
        duration_ms: int,
        provider_errors: list[str],
    ) -> None:
        if self.status is not SupplierDiscoveryRunStatus.RUNNING:
            raise InvalidSupplierDiscoveryState("Supplier discovery run is not active.")
        self.raw_candidates = candidates
        self.suppliers_found = len(candidates)
        self.search_duration_ms = max(duration_ms, 0)
        self.provider_errors = provider_errors[:100]
        self.current_stage = SupplierDiscoveryStage.DEDUPLICATION

    def save_deduplicated(
        self,
        processed_candidates: list[dict[str, Any]],
        *,
        duplicates_detected: int,
    ) -> None:
        if self.status is not SupplierDiscoveryRunStatus.RUNNING:
            raise InvalidSupplierDiscoveryState("Supplier discovery run is not active.")
        self.processed_candidates = processed_candidates
        self.duplicates_detected = max(duplicates_detected, 0)
        self.current_stage = SupplierDiscoveryStage.CONTACTS

    def mark_contacts_complete(self, contacts_found: int) -> None:
        if self.status is not SupplierDiscoveryRunStatus.RUNNING:
            raise InvalidSupplierDiscoveryState("Supplier discovery run is not active.")
        self.contacts_found = max(contacts_found, 0)
        self.current_stage = SupplierDiscoveryStage.MATCHING

    def mark_matching_complete(self, duration_ms: int) -> None:
        if self.status is not SupplierDiscoveryRunStatus.RUNNING:
            raise InvalidSupplierDiscoveryState("Supplier discovery run is not active.")
        self.matching_duration_ms = max(duration_ms, 0)
        self.current_stage = SupplierDiscoveryStage.REVIEW

    def complete(self) -> None:
        if self.status is not SupplierDiscoveryRunStatus.RUNNING:
            raise InvalidSupplierDiscoveryState("Supplier discovery run is not active.")
        self.status = SupplierDiscoveryRunStatus.COMPLETED
        self.current_stage = SupplierDiscoveryStage.COMPLETED
        self.completed_at = _now()
        self.error_type = None
        self.error_message = None

    def fail(self, error: Exception) -> None:
        self.status = SupplierDiscoveryRunStatus.FAILED
        self.completed_at = _now()
        self.error_type = type(error).__name__
        self.error_message = str(error)[:4000]

    def restart(self) -> None:
        self.status = SupplierDiscoveryRunStatus.QUEUED
        self.current_stage = SupplierDiscoveryStage.QUEUED
        self.error_type = None
        self.error_message = None
        self.completed_at = None

    def mark_reused(self, source_run_id: UUID) -> None:
        self.status = SupplierDiscoveryRunStatus.REUSED
        self.current_stage = SupplierDiscoveryStage.COMPLETED
        self.reused_from_run_id = source_run_id
        self.completed_at = _now()


@dataclass(frozen=True, slots=True)
class ProductSupplierMatch:
    tender_supplier_id: UUID
    product_id: UUID
    score: SupplierMatchScore
    components: dict[str, float]
    reasons: tuple[str, ...]
    algorithm_version: str
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=_now)

    def __post_init__(self) -> None:
        if not _clean(self.algorithm_version):
            raise ValidationError("Supplier matching algorithm version is required.")
        if not self.reasons:
            raise ValidationError("Supplier matching reasons are required.")


@dataclass(slots=True)
class SupplierMergeSuggestion:
    source_supplier_id: UUID
    target_supplier_id: UUID
    score: SupplierConfidence
    signals: tuple[str, ...]
    discovery_run_id: UUID | None = None
    id: UUID = field(default_factory=uuid4)
    status: MergeSuggestionStatus = MergeSuggestionStatus.PENDING
    reviewed_by_user_id: UUID | None = None
    reviewed_at: datetime | None = None
    created_at: datetime = field(default_factory=_now)

    def __post_init__(self) -> None:
        if self.source_supplier_id == self.target_supplier_id:
            raise SupplierMergeConflict("Merge suggestion requires two suppliers.")
        if not self.signals:
            raise ValidationError("Merge suggestion signals are required.")

    def accept(self, reviewer_user_id: UUID) -> None:
        if self.status is not MergeSuggestionStatus.PENDING:
            raise SupplierMergeConflict("Merge suggestion has already been reviewed.")
        self.status = MergeSuggestionStatus.ACCEPTED
        self.reviewed_by_user_id = reviewer_user_id
        self.reviewed_at = _now()

    def reject(self, reviewer_user_id: UUID) -> None:
        if self.status is not MergeSuggestionStatus.PENDING:
            raise SupplierMergeConflict("Merge suggestion has already been reviewed.")
        self.status = MergeSuggestionStatus.REJECTED
        self.reviewed_by_user_id = reviewer_user_id
        self.reviewed_at = _now()
