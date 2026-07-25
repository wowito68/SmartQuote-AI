from dataclasses import dataclass
from re import fullmatch

from app.domain.shared.exceptions import ValidationError

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
SHA256_PATTERN = r"^[a-fA-F0-9]{64}$"


@dataclass(frozen=True, slots=True)
class EmailAddress:
    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip().lower()
        if not fullmatch(EMAIL_PATTERN, normalized):
            raise ValidationError("Email address is invalid.")
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class FileHash:
    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip().lower()
        if not fullmatch(SHA256_PATTERN, normalized):
            raise ValidationError("File hash must be a SHA-256 hexadecimal value.")
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value

