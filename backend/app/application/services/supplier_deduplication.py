import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from urllib.parse import urlparse
from uuid import UUID

from app.application.ports.supplier_search_service import SupplierSuggestion
from app.domain.suppliers.entities import Supplier, SupplierContact
from app.domain.suppliers.value_objects import SupplierContactType

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalize_name(value: str | None) -> str:
    return _NON_ALNUM.sub(" ", (value or "").casefold()).strip()


def normalize_domain(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlparse(value if "://" in value else f"https://{value}")
    host = (parsed.hostname or "").casefold().strip(".")
    if host.startswith("www."):
        host = host[4:]
    return host or None


def normalize_phone(value: str | None) -> str | None:
    digits = "".join(character for character in (value or "") if character.isdigit())
    if len(digits) == 13 and digits.startswith("521"):
        digits = digits[3:]
    elif len(digits) == 12 and digits.startswith("52"):
        digits = digits[2:]
    return digits or None


@dataclass(frozen=True, slots=True)
class SupplierDuplicateResult:
    supplier_id: UUID
    score: float
    signals: tuple[str, ...]
    exact_identity: bool


class SupplierDeduplicationService:
    version = "1.0.0"
    suggestion_threshold = 0.40

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
            score += 0.60
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
            score += 0.35
            signals.append("same_email")

        suggested_phones = {
            normalize_phone(item.value)
            for item in suggestion.contacts
            if item.contact_type
            in {SupplierContactType.PHONE.value, SupplierContactType.WHATSAPP.value}
        }
        existing_phones = {
            normalize_phone(item.value)
            for item in existing_contacts
            if item.contact_type
            in {SupplierContactType.PHONE, SupplierContactType.WHATSAPP}
        }
        suggested_phones.discard(None)
        existing_phones.discard(None)
        if suggested_phones & existing_phones:
            score += 0.30
            signals.append("same_phone")

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
            score += legal_similarity * 0.30
            signals.append(f"legal_name_similarity:{legal_similarity:.3f}")
        if trade_similarity >= 0.65:
            score += trade_similarity * 0.25
            signals.append(f"trade_name_similarity:{trade_similarity:.3f}")

        exact_legal = bool(
            normalize_name(suggestion.legal_name)
            and normalize_name(suggestion.legal_name) == normalize_name(supplier.legal_name)
        )
        if exact_legal:
            exact_identity = True
            signals.append("same_legal_name")
        if "same_email" in signals and max(legal_similarity, trade_similarity) >= 0.65:
            exact_identity = True
        if "same_phone" in signals and max(legal_similarity, trade_similarity) >= 0.85:
            exact_identity = True

        return SupplierDuplicateResult(
            supplier_id=supplier.id,
            score=round(min(score, 1.0), 4),
            signals=tuple(dict.fromkeys(signals)),
            exact_identity=exact_identity,
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
