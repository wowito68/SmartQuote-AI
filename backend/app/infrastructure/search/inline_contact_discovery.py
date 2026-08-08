from app.application.ports.contact_discovery_service import ContactDiscoveryService
from app.application.ports.supplier_search_service import (
    SupplierContactSuggestion,
    SupplierSuggestion,
)

_ALLOWED_TYPES = {"email", "phone", "whatsapp", "contact_form"}


class InlineContactDiscoveryService(ContactDiscoveryService):
    """Use public contacts already returned by search; no crawling or guessing."""

    provider_name = "inline-search-result"
    provider_version = "1.0.0"

    def discover(self, suggestion: SupplierSuggestion) -> tuple[SupplierContactSuggestion, ...]:
        found: list[SupplierContactSuggestion] = []
        seen: set[tuple[str, str]] = set()
        for contact in suggestion.contacts:
            if contact.contact_type not in _ALLOWED_TYPES:
                continue
            if not contact.value.strip() or not contact.source_url.strip():
                continue
            identity = (contact.contact_type, contact.value.strip().casefold())
            if identity in seen:
                continue
            seen.add(identity)
            found.append(contact)
        return tuple(found)
