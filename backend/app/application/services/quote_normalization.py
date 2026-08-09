from decimal import Decimal

from app.domain.quotes.value_objects import DeliveryTime, Quantity, Unit


class QuoteNormalizer:
    """Deterministic normalization only. It never performs FX conversion or fills missing data."""

    @staticmethod
    def currency(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().upper()
        aliases = {"$MXN": "MXN", "M.N.": "MXN", "MN": "MXN", "US$": "USD", "USD$": "USD"}
        normalized = aliases.get(normalized, normalized)
        return normalized if len(normalized) == 3 and normalized.isalpha() else None

    @staticmethod
    def quantity(value: Decimal | None) -> Decimal | None:
        return Quantity(value).value if value is not None else None

    @staticmethod
    def unit(value: str | None) -> str | None:
        return Unit(value).value if value else None

    @staticmethod
    def delivery_days(value: int | None) -> int | None:
        return DeliveryTime(value).days if value is not None else None
