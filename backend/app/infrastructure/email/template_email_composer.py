from typing import Any

from app.application.ports.email_composer import ComposedEmail, EmailComposer
from app.application.ports.template_renderer import TemplateRenderer


class TemplateEmailComposer(EmailComposer):
    def __init__(self, renderer: TemplateRenderer) -> None:
        self._renderer = renderer

    def compose(
        self,
        template_name: str,
        template_version: str,
        context: dict[str, Any],
    ) -> ComposedEmail:
        rendered = self._renderer.render(template_name, template_version, context)
        return ComposedEmail(
            subject=rendered.subject,
            body=rendered.body,
            template_name=rendered.template_name,
            template_version=rendered.template_version,
            content_type=rendered.content_type,
        )
