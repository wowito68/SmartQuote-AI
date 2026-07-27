from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ComposedEmail:
    subject: str
    body: str
    template_name: str
    template_version: str
    content_type: str


class EmailComposer(ABC):
    @abstractmethod
    def compose(
        self,
        template_name: str,
        template_version: str,
        context: dict[str, Any],
    ) -> ComposedEmail: ...
