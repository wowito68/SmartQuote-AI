import re
from dataclasses import dataclass
from typing import Iterable

from app.application.ports.supplier_search_service import SupplierSearchProduct

_SPACE = re.compile(r"\s+")
_BRAND_KEYS = {"brand", "marca", "manufacturer", "fabricante"}
_MODEL_KEYS = {"model", "modelo", "part number", "numero de parte", "número de parte"}


def _clean(value: str | None) -> str:
    return _SPACE.sub(" ", (value or "").strip())


def _key(value: str) -> str:
    return _clean(value).casefold()


@dataclass(frozen=True, slots=True)
class SupplierQuery:
    text: str
    version: str
    terms: tuple[str, ...]


class SupplierQueryBuilder:
    """Build minimal, deterministic supplier-search queries from approved product data."""

    def __init__(
        self,
        version: str = "1.0.0",
        *,
        max_specifications: int = 6,
        max_description_chars: int = 120,
        max_query_chars: int = 512,
    ) -> None:
        self.version = version
        self.max_specifications = max(max_specifications, 0)
        self.max_description_chars = max(max_description_chars, 0)
        self.max_query_chars = max(max_query_chars, 64)

    def build(
        self,
        product: SupplierSearchProduct,
        *,
        country: str | None = None,
        city: str | None = None,
        keywords: Iterable[str] = (),
    ) -> SupplierQuery:
        terms: list[str] = []
        seen: set[str] = set()

        def add(value: str | None) -> None:
            cleaned = _clean(value)
            if not cleaned:
                return
            identity = cleaned.casefold()
            if identity in seen:
                return
            seen.add(identity)
            terms.append(cleaned)

        add(product.name)
        ordered_specs = sorted(product.specifications.items(), key=lambda item: _key(item[0]))
        brand_model = [
            (key, value)
            for key, value in ordered_specs
            if _key(key) in _BRAND_KEYS or _key(key) in _MODEL_KEYS
        ]
        other_specs = [item for item in ordered_specs if item not in brand_model]
        for _, value in brand_model + other_specs[: self.max_specifications]:
            add(value)
        add(product.category)
        if self.max_description_chars:
            add(_clean(product.description)[: self.max_description_chars])
        for keyword in keywords:
            add(keyword)
        add(city)
        add(country)

        accepted: list[str] = []
        for term in terms:
            candidate = " ".join((*accepted, term))
            if len(candidate) > self.max_query_chars:
                break
            accepted.append(term)
        return SupplierQuery(
            text=" ".join(accepted),
            version=self.version,
            terms=tuple(accepted),
        )
