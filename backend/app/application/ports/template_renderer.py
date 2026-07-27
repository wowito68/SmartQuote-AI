from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from app.domain.rfqs.entities import EmailTemplate


@dataclass(frozen=True, slots=True)
class RenderedTemplate:
    subject: str
    body: str
    template_name: str
    template_version: str
    content_type: str


class TemplateRenderer(ABC):
    @abstractmethod
    def render(
        self,
        template_name: str,
        template_version: str,
        context: dict[str, Any],
    ) -> RenderedTemplate: ...

    @abstractmethod
    def get_template(self, template_name: str, template_version: str) -> EmailTemplate: ...
