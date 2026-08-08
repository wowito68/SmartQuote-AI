import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from app.application.ports.supplier_search_service import (
    SupplierContactSuggestion,
    SupplierSearchRequest,
    SupplierSearchResponse,
    SupplierSearchService,
    SupplierSuggestion,
)
from app.application.services.supplier_normalization import normalize_http_url
from app.domain.suppliers.exceptions import SupplierSearchFailure

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+", re.IGNORECASE)


def _tokens(value: str | None) -> set[str]:
    return {token.casefold() for token in _TOKEN_PATTERN.findall(value or "") if len(token) > 1}


@dataclass(frozen=True, slots=True)
class SearchProviderContactRecord:
    contact_type: str
    value: str
    confidence: float
    source_url: str
    contact_name: str | None = None
    role: str | None = None


@dataclass(frozen=True, slots=True)
class SearchProviderRecord:
    legal_name: str | None
    trade_name: str | None
    website: str | None
    category: str | None
    country: str | None
    city: str | None
    description: str | None
    source_url: str
    source_title: str | None = None
    source_type: str = "directory"
    source_excerpt: str | None = None
    contacts: tuple[SearchProviderContactRecord, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)


class SearchProviderClient(Protocol):
    @property
    def provider_name(self) -> str: ...

    @property
    def provider_version(self) -> str: ...

    def search(
        self,
        *,
        query: str,
        category: str | None,
        country: str | None,
        max_results: int,
    ) -> tuple[SearchProviderRecord, ...]: ...


class JsonDirectorySearchClient:
    """Deterministic local directory client used by the current provider adapter."""

    provider_name = "json-directory"
    provider_version = "1.0.0"

    def __init__(self, directory_path: Path) -> None:
        self._directory_path = directory_path

    def _load(self) -> list[dict[str, Any]]:
        if not self._directory_path.exists():
            return []
        try:
            payload = json.loads(self._directory_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SupplierSearchFailure(
                f"Supplier directory could not be read: {self._directory_path}"
            ) from exc
        records = payload.get("suppliers", []) if isinstance(payload, dict) else payload
        if not isinstance(records, list):
            raise SupplierSearchFailure("Supplier directory must contain a list of suppliers.")
        return [item for item in records if isinstance(item, dict)]

    def search(
        self,
        *,
        query: str,
        category: str | None,
        country: str | None,
        max_results: int,
    ) -> tuple[SearchProviderRecord, ...]:
        query_tokens = _tokens(query)
        category_tokens = _tokens(category)
        ranked: list[tuple[float, SearchProviderRecord]] = []
        for raw in self._load():
            record_country = str(raw.get("country") or "").casefold()
            if country and record_country and record_country != country.casefold():
                continue
            searchable = " ".join(
                str(raw.get(key) or "")
                for key in (
                    "legal_name",
                    "trade_name",
                    "category",
                    "description",
                    "keywords",
                )
            )
            searchable_tokens = _tokens(searchable)
            if not searchable_tokens:
                continue
            query_overlap = len(query_tokens & searchable_tokens) / max(len(query_tokens), 1)
            category_overlap = len(category_tokens & searchable_tokens) / max(
                len(category_tokens), 1
            )
            score = query_overlap * 0.75 + category_overlap * 0.25
            if query_tokens and score <= 0:
                continue
            contacts = tuple(
                SearchProviderContactRecord(
                    contact_type=str(item.get("contact_type") or ""),
                    value=str(item.get("value") or ""),
                    confidence=float(item.get("confidence", 0.5)),
                    source_url=str(item.get("source_url") or raw.get("source_url") or ""),
                    contact_name=item.get("contact_name"),
                    role=item.get("role"),
                )
                for item in raw.get("contacts", [])
                if isinstance(item, dict)
            )
            record = SearchProviderRecord(
                legal_name=raw.get("legal_name"),
                trade_name=raw.get("trade_name"),
                website=raw.get("website"),
                category=raw.get("category"),
                country=raw.get("country"),
                city=raw.get("city"),
                description=raw.get("description"),
                source_url=str(raw.get("source_url") or ""),
                source_title=raw.get("source_title"),
                source_type=str(raw.get("source_type") or "directory"),
                source_excerpt=raw.get("source_excerpt"),
                contacts=contacts,
                metadata={"directory_score": round(score, 4)},
            )
            ranked.append((score, record))
        ranked.sort(
            key=lambda item: (
                item[0],
                item[1].trade_name or item[1].legal_name or "",
            ),
            reverse=True,
        )
        return tuple(record for _, record in ranked[:max_results])


class SearchProviderAdapter(SupplierSearchService):
    """Map a replaceable search-provider client into the Application search port."""

    def __init__(self, client: SearchProviderClient) -> None:
        self._client = client

    @property
    def provider_name(self) -> str:
        return self._client.provider_name

    @property
    def provider_version(self) -> str:
        return self._client.provider_version

    def search(self, request: SupplierSearchRequest) -> SupplierSearchResponse:
        query = request.query.strip()
        if not query:
            raise SupplierSearchFailure("Supplier search request requires a deterministic query.")
        try:
            records = self._client.search(
                query=query,
                category=request.product.category,
                country=request.country,
                max_results=request.max_results,
            )
        except SupplierSearchFailure:
            raise
        except Exception as exc:
            raise SupplierSearchFailure(str(exc)) from exc

        searched_at = datetime.now(UTC)
        suggestions: list[SupplierSuggestion] = []
        provider_errors: list[str] = []
        for record in records:
            if normalize_http_url(record.source_url) is None:
                provider_errors.append("Search result discarded because source URL is not HTTP(S).")
                continue
            suggestions.append(
                SupplierSuggestion(
                    legal_name=record.legal_name,
                    trade_name=record.trade_name,
                    website=record.website,
                    category=record.category,
                    country=record.country,
                    city=record.city,
                    description=record.description,
                    source_url=record.source_url,
                    source_title=record.source_title,
                    source_type=record.source_type,
                    source_excerpt=record.source_excerpt,
                    contacts=tuple(
                        SupplierContactSuggestion(
                            contact_type=contact.contact_type,
                            value=contact.value,
                            confidence=contact.confidence,
                            source_url=contact.source_url,
                            contact_name=contact.contact_name,
                            role=contact.role,
                        )
                        for contact in record.contacts
                    ),
                    metadata=dict(record.metadata),
                    query=query,
                    searched_at=searched_at,
                    search_provider=self.provider_name,
                    initial_score=float(record.metadata.get("directory_score", 0.0)),
                )
            )
        return SupplierSearchResponse(
            suggestions=tuple(suggestions),
            provider_errors=tuple(provider_errors),
            estimated_cost_usd=0.0,
        )
