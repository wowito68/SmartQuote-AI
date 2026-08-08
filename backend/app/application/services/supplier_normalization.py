import re
import unicodedata
from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse

from app.application.ports.supplier_search_service import SupplierSuggestion

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalize_name(value: str | None) -> str:
    decomposed = unicodedata.normalize("NFKD", value or "")
    ascii_value = "".join(char for char in decomposed if not unicodedata.combining(char))
    return _NON_ALNUM.sub(" ", ascii_value.casefold()).strip()


def normalize_domain(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlparse(value if "://" in value else f"https://{value}")
    if parsed.username or parsed.password:
        return None
    host = (parsed.hostname or "").casefold().strip(".")
    if host.startswith("www."):
        host = host[4:]
    return host or None


def normalize_http_url(value: str | None) -> str | None:
    if not value:
        return None
    raw = value.strip()
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    if parsed.username or parsed.password:
        return None
    host = parsed.hostname.casefold().strip(".")
    if host.startswith("www."):
        host = host[4:]
    port = parsed.port
    if port and not ((parsed.scheme == "http" and port == 80) or (parsed.scheme == "https" and port == 443)):
        host = f"{host}:{port}"
    path = parsed.path or ""
    if path != "/":
        path = path.rstrip("/")
    return urlunparse(("https", host, path, "", parsed.query, ""))


def normalize_email(value: str | None) -> str | None:
    candidate = (value or "").strip().casefold()
    if candidate.count("@") != 1 or candidate.startswith("@") or candidate.endswith("@"):
        return None
    return candidate


def normalize_phone(value: str | None) -> str | None:
    digits = "".join(character for character in (value or "") if character.isdigit())
    if len(digits) == 13 and digits.startswith("521"):
        digits = digits[3:]
    elif len(digits) == 12 and digits.startswith("52"):
        digits = digits[2:]
    return digits if len(digits) >= 7 else None


@dataclass(frozen=True, slots=True)
class NormalizedSupplierCandidate:
    original_name: str | None
    normalized_name: str
    original_url: str | None
    normalized_url: str | None
    normalized_domain: str | None
    normalized_emails: tuple[str, ...]
    normalized_phones: tuple[str, ...]
    normalized_country: str | None
    normalized_city: str | None


class SupplierCandidateNormalizer:
    version = "1.0.0"

    def normalize(self, suggestion: SupplierSuggestion) -> NormalizedSupplierCandidate:
        original_name = suggestion.trade_name or suggestion.legal_name
        emails = sorted(
            {
                normalized
                for contact in suggestion.contacts
                if contact.contact_type == "email"
                and (normalized := normalize_email(contact.value)) is not None
            }
        )
        phones = sorted(
            {
                normalized
                for contact in suggestion.contacts
                if contact.contact_type in {"phone", "whatsapp"}
                and (normalized := normalize_phone(contact.value)) is not None
            }
        )
        return NormalizedSupplierCandidate(
            original_name=original_name,
            normalized_name=normalize_name(original_name),
            original_url=suggestion.website,
            normalized_url=normalize_http_url(suggestion.website),
            normalized_domain=normalize_domain(suggestion.website),
            normalized_emails=tuple(emails),
            normalized_phones=tuple(phones),
            normalized_country=(suggestion.country or "").strip().casefold() or None,
            normalized_city=normalize_name(suggestion.city) or None,
        )
