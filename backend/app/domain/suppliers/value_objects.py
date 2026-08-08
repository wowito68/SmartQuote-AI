from dataclasses import dataclass
from enum import StrEnum

from app.domain.shared.exceptions import ValidationError


class SupplierStatus(StrEnum):
    CANDIDATE = "candidate"
    CONTACTS_FOUND = "contacts_found"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    MERGED = "merged"
    CONTACTED = "contacted"
    RESPONDED = "responded"
    INACTIVE = "inactive"


class SupplierContactType(StrEnum):
    EMAIL = "email"
    PHONE = "phone"
    WHATSAPP = "whatsapp"
    CONTACT_FORM = "contact_form"


class SupplierDiscoveryRunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    REUSED = "reused"


class SupplierDiscoveryStage(StrEnum):
    QUEUED = "queued"
    SEARCH = "supplier_discovery"
    DEDUPLICATION = "supplier_deduplication"
    CONTACTS = "contact_discovery"
    MATCHING = "supplier_matching"
    REVIEW = "pending_supplier_review"
    COMPLETED = "approved_suppliers_ready"


class MergeSuggestionStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class SupplierConfidence:
    value: float

    def __post_init__(self) -> None:
        if not 0 <= self.value <= 1:
            raise ValidationError("Supplier confidence must be between zero and one.")


@dataclass(frozen=True, slots=True)
class SupplierMatchScore:
    value: float

    def __post_init__(self) -> None:
        if not 0 <= self.value <= 100:
            raise ValidationError("Supplier match score must be between zero and one hundred.")
