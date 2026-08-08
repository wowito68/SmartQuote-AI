import re
from dataclasses import dataclass
from typing import Any

from app.domain.suppliers.entities import Supplier

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_STOPWORDS = {
    "de",
    "del",
    "la",
    "el",
    "los",
    "las",
    "y",
    "con",
    "para",
    "por",
    "un",
    "una",
    "the",
    "of",
    "and",
}


def _tokens(value: str | None) -> set[str]:
    if not value:
        return set()
    return {
        token.casefold()
        for token in _TOKEN_PATTERN.findall(value)
        if len(token) > 1 and token.casefold() not in _STOPWORDS
    }


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


@dataclass(frozen=True, slots=True)
class SupplierMatchingWeights:
    name: float = 35.0
    category: float = 25.0
    keywords: float = 20.0
    specifications: float = 20.0

    def __post_init__(self) -> None:
        if round(self.name + self.category + self.keywords + self.specifications, 6) != 100.0:
            raise ValueError("Supplier matching weights must sum to 100.")


@dataclass(frozen=True, slots=True)
class SupplierMatchResult:
    score: float
    components: dict[str, float]
    reasons: tuple[str, ...]


class SupplierMatchingService:
    """Deterministic baseline. Brand/model are evaluated through specification overlap."""

    def __init__(
        self,
        version: str = "1.0.0",
        weights: SupplierMatchingWeights | None = None,
    ) -> None:
        self.version = version
        self.weights = weights or SupplierMatchingWeights()

    def calculate(self, product: dict[str, Any], supplier: Supplier) -> SupplierMatchResult:
        product_name = str(product.get("name") or "")
        product_category = str(product.get("category") or "")
        product_description = str(product.get("description") or "")
        specifications = product.get("specifications") or {}
        if not isinstance(specifications, dict):
            specifications = {}

        supplier_name_text = " ".join(
            value for value in (supplier.legal_name, supplier.trade_name) if value
        )
        supplier_text = " ".join(
            value
            for value in (
                supplier_name_text,
                supplier.category,
                supplier.description,
            )
            if value
        )

        product_name_tokens = _tokens(product_name)
        supplier_name_tokens = _tokens(supplier_name_text)
        name_similarity = _jaccard(product_name_tokens, supplier_name_tokens)
        if product_name.casefold() in supplier_text.casefold() and product_name.strip():
            name_similarity = max(name_similarity, 0.85)
        name_score = round(name_similarity * self.weights.name, 4)

        category_similarity = _jaccard(_tokens(product_category), _tokens(supplier.category))
        if (
            product_category
            and supplier.category
            and product_category.casefold().strip() == supplier.category.casefold().strip()
        ):
            category_similarity = 1.0
        category_score = round(category_similarity * self.weights.category, 4)

        product_keyword_text = " ".join(
            [product_name, product_description, product_category]
            + [f"{key} {value}" for key, value in specifications.items()]
        )
        keyword_similarity = _jaccard(_tokens(product_keyword_text), _tokens(supplier_text))
        keyword_score = round(keyword_similarity * self.weights.keywords, 4)

        specification_tokens = _tokens(
            " ".join(f"{key} {value}" for key, value in specifications.items())
        )
        supplier_tokens = _tokens(supplier_text)
        specification_ratio = (
            len(specification_tokens & supplier_tokens) / len(specification_tokens)
            if specification_tokens
            else 0.0
        )
        specification_score = round(specification_ratio * self.weights.specifications, 4)

        components = {
            "name": name_score,
            "category": category_score,
            "keywords": keyword_score,
            "specifications": specification_score,
        }
        score = round(min(sum(components.values()), 100.0), 2)
        reasons = (
            f"Name similarity contributed {name_score:.2f}/{self.weights.name:.0f}.",
            f"Category similarity contributed {category_score:.2f}/{self.weights.category:.0f}.",
            f"Keyword overlap contributed {keyword_score:.2f}/{self.weights.keywords:.0f}.",
            "Specification overlap (including brand/model when supplied as specifications) "
            f"contributed {specification_score:.2f}/{self.weights.specifications:.0f}.",
        )
        return SupplierMatchResult(score, components, reasons)
