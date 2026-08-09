import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.domain.quotes.value_objects import ComplianceStatus, ProductMatchStatus


def _tokens(value: str | None) -> set[str]:
    if not value:
        return set()
    return {
        token
        for token in re.findall(r"[a-z0-9]+", value.casefold())
        if len(token) > 1
    }


def _normalized_text(value: str | None) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", (value or "").casefold()))


def _similarity(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


@dataclass(frozen=True, slots=True)
class ProductMatchResult:
    product_id: UUID | None
    status: ProductMatchStatus
    score: float
    reason: str


class QuoteProductMatcher:
    MATCHED_THRESHOLD = 0.90
    POSSIBLE_THRESHOLD = 0.55

    def match(
        self,
        products: tuple[dict[str, Any], ...],
        *,
        name: str,
        description: str | None,
        brand: str | None,
        model: str | None,
        unit: str | None,
        quantity: Decimal | None,
    ) -> ProductMatchResult:
        quote_identity = _normalized_text(name)
        quote_tokens = _tokens(
            " ".join(filter(None, [name, description, brand, model]))
        )
        candidates: list[tuple[float, UUID, str, str]] = []
        for product in products:
            product_id = product.get("product_id")
            if not product_id:
                continue
            product_name = str(product.get("name") or "product")
            requested_identity = _normalized_text(product_name)
            product_text = " ".join(
                str(value)
                for value in (
                    product.get("name"),
                    product.get("description"),
                    product.get("category"),
                    " ".join(
                        f"{key} {value}"
                        for key, value in (
                            product.get("specifications") or {}
                        ).items()
                    ),
                )
                if value
            )
            lexical = _similarity(quote_tokens, _tokens(product_text))
            unit_bonus = 0.0
            requested_unit = str(product.get("unit") or "").casefold().strip()
            if unit and requested_unit and unit.casefold().strip() == requested_unit:
                unit_bonus = 0.08
            quantity_bonus = 0.0
            requested_quantity = product.get("quantity")
            if quantity is not None and requested_quantity is not None:
                try:
                    requested = Decimal(str(requested_quantity))
                    if (
                        requested > 0
                        and abs(quantity - requested) / requested <= Decimal("0.05")
                    ):
                        quantity_bonus = 0.07
                except (ArithmeticError, TypeError, ValueError):
                    pass
            if (
                quote_identity
                and requested_identity
                and (
                    quote_identity == requested_identity
                    or quote_identity in requested_identity
                    or requested_identity in quote_identity
                )
            ):
                score = 1.0
            else:
                score = min(1.0, lexical * 0.85 + unit_bonus + quantity_bonus)
            candidates.append(
                (
                    score,
                    UUID(str(product_id)),
                    product_name,
                    requested_identity,
                )
            )
        if not candidates:
            return ProductMatchResult(
                None,
                ProductMatchStatus.UNMATCHED,
                0.0,
                "No approved products are available for matching.",
            )
        candidates.sort(key=lambda item: (-item[0], str(item[1])))
        score, product_id, product_name, _ = candidates[0]
        second = candidates[1][0] if len(candidates) > 1 else 0.0
        if score >= self.MATCHED_THRESHOLD and score - second >= 0.10:
            return ProductMatchResult(
                product_id,
                ProductMatchStatus.MATCHED,
                score,
                (
                    "Strong deterministic match with requested product "
                    f"'{product_name}'."
                ),
            )
        if score >= self.POSSIBLE_THRESHOLD:
            return ProductMatchResult(
                product_id,
                ProductMatchStatus.POSSIBLE_MATCH,
                score,
                (
                    f"Possible match with '{product_name}'; "
                    "human confirmation is required."
                ),
            )
        return ProductMatchResult(
            None,
            ProductMatchStatus.UNMATCHED,
            score,
            "No requested product reached the deterministic matching threshold.",
        )


class TechnicalComplianceEvaluator:
    def evaluate(
        self,
        requested: dict[str, str],
        quoted: dict[str, str],
    ) -> tuple[ComplianceStatus, str]:
        if not requested:
            return (
                ComplianceStatus.UNKNOWN,
                "No structured requested specifications are available.",
            )
        normalized_quoted = {
            str(key).casefold().strip(): str(value).casefold().strip()
            for key, value in quoted.items()
        }
        checked = 0
        matches = 0
        conflicts: list[str] = []
        for key, expected in requested.items():
            normalized_key = str(key).casefold().strip()
            actual = normalized_quoted.get(normalized_key)
            if actual is None:
                continue
            checked += 1
            expected_norm = str(expected).casefold().strip()
            if (
                actual == expected_norm
                or expected_norm in actual
                or actual in expected_norm
            ):
                matches += 1
            else:
                conflicts.append(
                    f"{key}: requested {expected}, quoted {quoted.get(key, actual)}"
                )
        if conflicts:
            return ComplianceStatus.NON_COMPLIANT, "; ".join(conflicts)
        if checked == 0:
            return (
                ComplianceStatus.UNKNOWN,
                (
                    "The quote does not provide evidence for the requested "
                    "specifications."
                ),
            )
        if checked == len(requested) and matches == checked:
            return (
                ComplianceStatus.COMPLIANT,
                "All structured requested specifications found in the quote match.",
            )
        return (
            ComplianceStatus.PARTIAL,
            (
                "Only part of the requested specifications are explicitly "
                "supported by the quote."
            ),
        )
