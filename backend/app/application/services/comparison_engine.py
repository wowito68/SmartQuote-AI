from collections import defaultdict
from decimal import Decimal
from typing import Any

from app.domain.quotes.entities import QuoteItem


class ComparisonEngine:
    """Fixed, deterministic MVP scoring. It is advisory and never awards a purchase."""

    TECHNICAL_WEIGHT = Decimal("0.50")
    PRICE_WEIGHT = Decimal("0.35")
    DELIVERY_WEIGHT = Decimal("0.15")

    def build(
        self,
        entries: list[tuple[str, str, QuoteItem]],
    ) -> tuple[tuple[dict[str, Any], ...], dict[str, Any]]:
        if not entries:
            raise ValueError("At least one approved quote item is required.")

        by_product: dict[str, list[tuple[str, str, QuoteItem]]] = defaultdict(list)
        for supplier_id, supplier_name, item in entries:
            key = str(item.catalog_product_id) if item.catalog_product_id else item.product_name.casefold()
            by_product[key].append((supplier_id, supplier_name, item))

        rows: list[dict[str, Any]] = []
        supplier_scores: dict[str, list[Decimal]] = defaultdict(list)
        supplier_names: dict[str, str] = {}
        warnings: list[str] = []

        for product_entries in by_product.values():
            comparable_prices = [
                item.total_price
                for _, _, item in product_entries
                if item.total_price is not None and item.total_price > 0
            ]
            comparable_delivery = [
                item.delivery_days
                for _, _, item in product_entries
                if item.delivery_days is not None and item.delivery_days >= 0
            ]
            minimum_price = min(comparable_prices) if comparable_prices else None
            minimum_delivery = min(comparable_delivery) if comparable_delivery else None

            for supplier_id, supplier_name, item in product_entries:
                supplier_names[supplier_id] = supplier_name
                row_warnings: list[str] = []
                if item.technical_compliance is True:
                    technical = Decimal("1")
                elif item.technical_compliance is False:
                    technical = Decimal("0")
                else:
                    technical = Decimal("0.5")
                    row_warnings.append("Technical compliance is incomplete or unverified.")

                if item.total_price is not None and item.total_price > 0 and minimum_price:
                    price = min(Decimal("1"), minimum_price / item.total_price)
                else:
                    price = Decimal("0.5")
                    row_warnings.append("Price is incomplete or not comparable.")

                if item.delivery_days is not None and minimum_delivery is not None:
                    if item.delivery_days == 0:
                        delivery = Decimal("1")
                    else:
                        baseline = max(minimum_delivery, 1)
                        delivery = min(Decimal("1"), Decimal(baseline) / Decimal(item.delivery_days))
                else:
                    delivery = Decimal("0.5")
                    row_warnings.append("Delivery time is incomplete.")

                score = (
                    technical * self.TECHNICAL_WEIGHT
                    + price * self.PRICE_WEIGHT
                    + delivery * self.DELIVERY_WEIGHT
                ) * Decimal("100")
                score = score.quantize(Decimal("0.01"))
                supplier_scores[supplier_id].append(score)
                warnings.extend(row_warnings)
                rows.append(
                    {
                        "catalog_product_id": str(item.catalog_product_id) if item.catalog_product_id else None,
                        "product": item.product_name,
                        "supplier_id": supplier_id,
                        "supplier": supplier_name,
                        "brand": item.brand,
                        "model": item.model,
                        "quantity": str(item.quantity) if item.quantity is not None else None,
                        "unit_price": str(item.unit_price) if item.unit_price is not None else None,
                        "total_price": str(item.total_price) if item.total_price is not None else None,
                        "currency": item.currency,
                        "delivery_days": item.delivery_days,
                        "technical_compliance": item.technical_compliance,
                        "notes": item.notes,
                        "source": {
                            "quote_id": str(item.quote_id),
                            "page": item.source_page,
                            "evidence_fragment": item.evidence_fragment,
                            "confidence": item.confidence,
                        },
                        "criteria": {
                            "technical": float(technical),
                            "price": float(price),
                            "delivery": float(delivery),
                        },
                        "score": float(score),
                        "warnings": row_warnings,
                    }
                )

        ranked = sorted(
            (
                (
                    (sum(scores, Decimal("0")) / Decimal(len(scores))).quantize(Decimal("0.01")),
                    supplier_id,
                )
                for supplier_id, scores in supplier_scores.items()
            ),
            key=lambda value: (-value[0], value[1]),
        )
        best_score, best_supplier_id = ranked[0]
        considered_products = sorted({row["product"] for row in rows})
        recommendation = {
            "recommended_supplier_id": best_supplier_id,
            "recommended_supplier": supplier_names[best_supplier_id],
            "products_considered": considered_products,
            "criteria": {
                "technical_compliance_weight": float(self.TECHNICAL_WEIGHT),
                "price_weight": float(self.PRICE_WEIGHT),
                "delivery_weight": float(self.DELIVERY_WEIGHT),
            },
            "score": float(best_score),
            "explanation": (
                "The supplier has the highest deterministic MVP score across technical "
                "compliance, price and delivery time. Extracted values remain subject to review."
            ),
            "warnings": sorted(set(warnings)),
            "human_review_required": True,
            "decision": "recommendation_only",
        }
        return tuple(rows), recommendation
