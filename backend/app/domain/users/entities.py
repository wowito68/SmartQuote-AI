from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.domain.shared.exceptions import ValidationError
from app.domain.shared.value_objects import EmailAddress


@dataclass(slots=True)
class User:
    email: EmailAddress
    full_name: str
    role: str = "buyer"
    is_active: bool = True
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.full_name.strip():
            raise ValidationError("User full name is required.")
        if not self.role.strip():
            raise ValidationError("User role is required.")
        self.full_name = self.full_name.strip()
        self.role = self.role.strip()

