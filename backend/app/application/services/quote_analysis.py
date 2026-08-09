import math
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.domain.quotes.value_objects import ComplianceStatus, MatchStatus, Unit


@dataclass(frozen=True, slots=True)
class ProductMatchResult:
    product_id: UUID | None
    status: MatchStatus
    score: float
    reason: str


def _tokens(value: str | None) -> set[str]:
    if not value:
        return set()
    return {
        token
        for token in re.findall(r"[\w-]+", value.casefold())
        if len(token) > 1
    }


def _similarity(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


class QuoteProductMatcher:
    """Deterministic, explainable matching. AI output is never accepted as identity truth."""

    def match(
        self,
        *,
        item_name: str,
        item_description: str | None,
        item_unit: str | None,
        item_quantity: Decimal | None,
        item_brand: str | None,
        item_model: str | None,
        products: tuple[dict[str, Any], ...],
    ) -> ProductMatchResult:
        item_tokens = _tokens(" ".join(filter(None, (item_name, item_description, item_brand, item_model))))
        candidates: list[tuple[float, UUID, list[str]]] = []
        for product in products:
            raw_id = product.get("product_id")
            if not raw_id:
                continue
            product_tokens = _tokens(
                " ".join(
                    str(value)
                    for value in (
                        product.get("name"),
                        product.get("description"),
                        product.get("category"),
                    )
                    if value
                )
            )
            lexical = _similarity(item_tokens, product_tokens)
            score = lexical * 0.75
            reasons = [f"lexical={lexical:.2f}"]
            requested_unit = product.get("unit")
            if item_unit and requested_unit:
                try:
                    same_unit = Unit(item_unit).value == Unit(str(requested_unit)).value
                except Exception:
                    same_unit = item_unit.casefold() == str(requested_unit).casefold()
                if same_unit:
                    score += 0.10
                    reasons.append("unit matches")
                else:
                    score -= 0.10
                    reasons.append("unit differs")
            requested_quantity = product.get("quantity")
            if item_quantity is not None and requested_quantity not in (None, ""):
                try:
                    rq = Decimal(str(requested_quantity))
                    if rq > 0:
                        ratio = float(min(item_quantity, rq) / max(item_quantity, rq))
                        score += 0.05 * ratio
                        reasons.append(f"quantity similarity={ratio:.2f}")
                except Exception:
                    pass
            specifications = product.get("specifications") or {}
            if isinstance(specifications, dict) and specifications:
                spec_tokens = _tokens(" ".join(f"{k} {v}" for k, v in specifications.items()))
                spec_score = _similarity(item_tokens, spec_tokens)
                score += 0.10 * spec_score
                reasons.append(f"spec overlap={spec_score:.2f}")
            candidates.append((max(0.0, min(score, 1.0)), UUID(str(raw_id)), reasons))
        if not candidates:
            return ProductMatchResult(None, MatchStatus.UNMATCHED, 0.0, "No approved product candidates.")
        candidates.sort(key=lambda value: (value[0], str(value[1])), reverse=True)
        best_score, best_id, reasons = candidates[0]
        second = candidates[1][0] if len(candidates) > 1 else 0.0
        if best_score >= 0.86 and best_score - second >= 0.12:
            status = MatchStatus.MATCHED
        elif best_score >= 0.58:
            status = MatchStatus.POSSIBLE_MATCH
        else:
            status = MatchStatus.UNMATCHED
            best_id = None
        return ProductMatchResult(best_id, status, round(best_score, 4), "; ".join(reasons))


class TechnicalComplianceEvaluator:
    def evaluate(
        self,
        required: dict[str, str],
        quoted: dict[str, str],
    ) -> tuple[ComplianceStatus, tuple[str, ...]]:
        if not required:
            return ComplianceStatus.UNKNOWN, ("No structured requirements available.",)
        if not quoted:
            return ComplianceStatus.UNKNOWN, ("Quote does not state technical specifications.",)
        matched = 0
        conflicts: list[str] = []
        missing: list[str] = []
        normalized_quoted = {str(k).casefold(): str(v).casefold() for k, v in quoted.items()}
        for key, value in required.items():
            qvalue = normalized_quoted.get(str(key).casefold())
            if qvalue is None:
                missing.append(str(key))
            elif str(value).casefold() in qvalue or qvalue in str(value).casefold():
                matched += 1
            else:
                conflicts.append(f"{key}: requested {value}, quoted {qvalue}")
        if conflicts:
            return ComplianceStatus.NON_COMPLIANT, tuple(conflicts)
        if missing:
            status = ComplianceStatus.PARTIAL if matched else ComplianceStatus.UNKNOWN
            return status, tuple(f"Missing evidence for {key}" for key in missing)
        return ComplianceStatus.COMPLIANT, ("All structured requirements are explicitly supported.",)


def price_warnings(
    quantity: Decimal | None,
    unit_price: Decimal | None,
    total_price: Decimal | None,
) -> tuple[str, ...]:
    if quantity is None or unit_price is None or total_price is None:
        return ()
    expected = quantity * unit_price
    tolerance = max(Decimal("0.01"), abs(expected) * Decimal("0.01"))
    if not math.isfinite(float(expected)) or abs(total_price - expected) > tolerance:
        return ("PRICE_CALCULATION_MISMATCH",)
    return ()
