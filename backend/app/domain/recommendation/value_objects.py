from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from app.domain.shared.exceptions import ValidationError


class RecommendationStatus(StrEnum):
    READY = "ready"
    WITHHELD = "withheld"


@dataclass(frozen=True, slots=True)
class RecommendationWeights:
    technical: Decimal
    price: Decimal
    delivery: Decimal

    def __post_init__(self) -> None:
        technical = Decimal(str(self.technical))
        price = Decimal(str(self.price))
        delivery = Decimal(str(self.delivery))
        values = (technical, price, delivery)
        if any(value < 0 or value > 1 for value in values):
            raise ValidationError("Recommendation weights must be between zero and one.")
        if abs(sum(values, Decimal("0")) - Decimal("1")) > Decimal("0.0001"):
            raise ValidationError("Recommendation weights must sum to one.")
        object.__setattr__(self, "technical", technical)
        object.__setattr__(self, "price", price)
        object.__setattr__(self, "delivery", delivery)

    def canonical(self) -> str:
        return "|".join(
            format(value.normalize(), "f") for value in (self.technical, self.price, self.delivery)
        )

    def as_dict(self) -> dict[str, str]:
        return {
            "technical": str(self.technical),
            "price": str(self.price),
            "delivery": str(self.delivery),
        }
