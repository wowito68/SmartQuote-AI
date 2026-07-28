import re
from dataclasses import dataclass
from enum import StrEnum

from app.domain.shared.exceptions import ValidationError

_EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class RfqStatus(StrEnum):
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    QUEUED = "queued"
    SENDING = "sending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    CANCELLED = "cancelled"


class EmailMessageStatus(StrEnum):
    QUEUED = "queued"
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"


class OutboundLogResult(StrEnum):
    RECORDED = "recorded"
    SUCCESS = "success"
    FAILURE = "failure"


@dataclass(frozen=True, slots=True)
class EmailAddress:
    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip().casefold()
        if len(normalized) > 320 or not _EMAIL_PATTERN.fullmatch(normalized):
            raise ValidationError("Email address is invalid.")
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value
