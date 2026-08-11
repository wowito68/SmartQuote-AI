from decimal import Decimal, InvalidOperation
from typing import Any

from app.domain.comparison.value_objects import (
    DeliveryTime,
    Money,
    NormalizedCompliance,
    Quantity,
    QuantityComparisonStatus,
)
from app.domain.quotes.entities import QuoteItem
from app.domain.quotes.value_objects import ComplianceStatus


class ComparisonNormalizer:
    """Normalize comparison fields without FX or unsafe unit conversion."""

    _UNIT_ALIASES = {
        "piece": "piece",
        "pieces": "piece",
        "pieza": "piece",
        "piezas": "piece",
        "pza": "piece",
        "pzas": "piece",
        "pc": "piece",
        "pcs": "piece",
        "unit": "piece",
        "unidad": "piece",
        "unidades": "piece",
        "box": "box",
        "boxes": "box",
        "caja": "box",
        "cajas": "box",
        "pack": "pack",
        "packs": "pack",
        "package": "pack",
        "paquete": "pack",
        "paquetes": "pack",
        "kg": "kg",
        "kilogram": "kg",
        "kilograms": "kg",
        "kilogramo": "kg",
        "kilogramos": "kg",
        "l": "l",
        "lt": "l",
        "liter": "l",
        "liters": "l",
        "litro": "l",
        "litros": "l",
        "m": "m",
        "meter": "m",
        "meters": "m",
        "metro": "m",
        "metros": "m",
    }

    @classmethod
    def normalize_unit(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.split()).casefold()
        if not cleaned:
            return None
        return cls._UNIT_ALIASES.get(cleaned, cleaned)

    @staticmethod
    def decimal(value: Any) -> Decimal | None:
        if value is None or value == "":
            return None
        try:
            parsed = Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            return None
        return parsed if parsed >= 0 else None

    @classmethod
    def quantity(cls, value: Any, unit: str | None) -> Quantity:
        return Quantity(cls.decimal(value), cls.normalize_unit(unit))

    @staticmethod
    def money(amount: Decimal | None, currency: str | None) -> Money:
        normalized_currency = currency.strip().upper() if currency else None
        if normalized_currency and (
            len(normalized_currency) != 3 or not normalized_currency.isalpha()
        ):
            normalized_currency = None
        return Money(amount, normalized_currency)

    @staticmethod
    def compliance(status: ComplianceStatus) -> NormalizedCompliance:
        mapping = {
            ComplianceStatus.COMPLIANT: NormalizedCompliance.COMPLIANT,
            ComplianceStatus.PARTIAL: NormalizedCompliance.PARTIALLY_COMPLIANT,
            ComplianceStatus.NON_COMPLIANT: NormalizedCompliance.NON_COMPLIANT,
            ComplianceStatus.UNKNOWN: NormalizedCompliance.UNKNOWN,
        }
        return mapping[status]

    @staticmethod
    def delivery(item: QuoteItem, quote_delivery_days: int | None) -> DeliveryTime:
        days = item.delivery_days if item.delivery_days is not None else quote_delivery_days
        raw = item.original_extracted or {}
        original_text: str | None = None
        for key in ("delivery_text", "delivery_time", "delivery"):
            value = raw.get(key)
            if isinstance(value, str) and value.strip():
                original_text = value
                break
        return DeliveryTime(
            days=days,
            original_text=original_text,
            normalized=days is not None,
        )

    @staticmethod
    def compare_quantity(
        requested: Quantity,
        quoted: Quantity,
    ) -> QuantityComparisonStatus:
        if requested.value is None or quoted.value is None:
            return QuantityComparisonStatus.UNKNOWN
        if requested.unit is None or quoted.unit is None:
            return QuantityComparisonStatus.UNKNOWN
        if requested.unit != quoted.unit:
            return QuantityComparisonStatus.UNIT_MISMATCH
        if requested.value != quoted.value:
            return QuantityComparisonStatus.QUANTITY_MISMATCH
        return QuantityComparisonStatus.MATCHED
