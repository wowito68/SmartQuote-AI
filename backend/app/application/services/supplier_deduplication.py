from dataclasses import dataclass
from difflib import SequenceMatcher
from enum import StrEnum
from uuid import UUID

from app.application.ports.supplier_search_service import SupplierSuggestion
from app.application.services.supplier_normalization import (
    normalize_domain,
    normalize_name,
    normalize_phone,
)
from app.domain.suppliers.entities import Supplier, SupplierContact
from app.domain.suppliers.value_objects import SupplierContactType


class SupplierDuplicateStatus(StrEnum):
    DUPLICATE = "duplicate"
    POSSIBLE_DUPLICATE = "possible_duplicate"
    UNIQUE = "unique"


@dataclass(frozen=True, slots=True)
class SupplierDeduplicationWeights:
    same_domain: float = 0.60
    same_email: float = 0.35
    same_phone: float = 0.30
    legal_name_similarity: float = 0.30
    trade_name_similarity: float = 0.25
    same_city: float = 0.05


@dataclass(frozen=True, slots=True)
class SupplierDuplicateResult:
    supplier_id: UUID
    score: float
    signals: tuple[str, ...]
    exact_identity: bool
    status: SupplierDuplicateStatus


class SupplierDeduplicationService:
    version = "2.0.0"
    suggestion_threshold = 0.40

    def __init__(
        self,
        weights: SupplierDeduplicationWeights | None = None,
        *,
        suggestion_threshold: float | None = None,
    ) -> None:
        self.weights = weights or SupplierDeduplicationWeights()
        if suggestion_threshold is not None:
            self.suggestion_threshold = suggestion_threshold

    def compare(
        self,
        suggestion: SupplierSuggestion,
        supplier: Supplier,
        existing_contacts: list[SupplierContact],
    ) -> SupplierDuplicateResult:
        signals: list[str] = []
        score = 0.0
        exact_identity = False

        suggestion_domain = normalize_domain(suggestion.website)
        if suggestion_domain and suggestion_domain == supplier.normalized_domain:
            score += self.weights.same_domain
            signals.append("same_web_domain")
            exact_identity = True

        suggested_emails = {
            item.value.casefold()
            for item in suggestion.contacts
            if item.contact_type == SupplierContactType.EMAIL.value
        }
        existing_emails = {
            item.value.casefold()
            for item in existing_contacts
            if item.contact_type is SupplierContactType.EMAIL
        }
        if suggested_emails & existing_emails:
            score += self.weights.same_email
            signals.append("same_email")
            exact_identity = True

        suggested_phones = {
            normalize_phone(item.value)
            for item in suggestion.contacts
            if item.contact_type
            in {SupplierContactType.PHONE.value, SupplierContactType.WHATSAPP.value}
        }
        existing_phones = {
            normalize_phone(item.value)
            for item in existing_contacts
            if item.contact_type in {SupplierContactType.PHONE, SupplierContactType.WHATSAPP}
        }
        suggested_phones.discard(None)
        existing_phones.discard(None)
        if suggested_phones & existing_phones:
            score += self.weights.same_phone
            signals.append("same_phone")
            exact_identity = True

        legal_similarity = SequenceMatcher(
            None,
            normalize_name(suggestion.legal_name),
            normalize_name(supplier.legal_name),
        ).ratio()
        trade_similarity = SequenceMatcher(
            None,
            normalize_name(suggestion.trade_name),
            normalize_name(supplier.trade_name),
        ).ratio()
        if legal_similarity >= 0.65:
            score += legal_similarity * self.weights.legal_name_similarity
            signals.append(f"legal_name_similarity:{legal_similarity:.3f}")
        if trade_similarity >= 0.65:
            score += trade_similarity * self.weights.trade_name_similarity
            signals.append(f"trade_name_similarity:{trade_similarity:.3f}")

        exact_legal = bool(
            normalize_name(suggestion.legal_name)
            and normalize_name(suggestion.legal_name) == normalize_name(supplier.legal_name)
        )
        if exact_legal:
            exact_identity = True
            signals.append("same_legal_name")

        if (
            suggestion.city
            and supplier.city
            and normalize_name(suggestion.city) == normalize_name(supplier.city)
        ):
            score += self.weights.same_city
            signals.append("same_city")

        bounded = round(min(score, 1.0), 4)
        if exact_identity:
            status = SupplierDuplicateStatus.DUPLICATE
        elif bounded >= self.suggestion_threshold:
            status = SupplierDuplicateStatus.POSSIBLE_DUPLICATE
        else:
            status = SupplierDuplicateStatus.UNIQUE
        return SupplierDuplicateResult(
            supplier_id=supplier.id,
            score=bounded,
            signals=tuple(dict.fromkeys(signals)),
            exact_identity=exact_identity,
            status=status,
        )

    def find_best(
        self,
        suggestion: SupplierSuggestion,
        suppliers: list[Supplier],
        contacts_by_supplier: dict[UUID, list[SupplierContact]],
    ) -> SupplierDuplicateResult | None:
        results = [
            self.compare(suggestion, supplier, contacts_by_supplier.get(supplier.id, []))
            for supplier in suppliers
            if supplier.merged_into_supplier_id is None
        ]
        results = [result for result in results if result.signals]
        if not results:
            return None
        return max(results, key=lambda item: (item.score, item.exact_identity))
