import json
from pathlib import Path
from typing import Any

from jinja2 import StrictUndefined
from jinja2.exceptions import TemplateError
from jinja2.sandbox import SandboxedEnvironment

from app.application.ports.template_renderer import RenderedTemplate, TemplateRenderer
from app.domain.rfqs.entities import EmailTemplate
from app.domain.rfqs.exceptions import EmailCompositionError, EmailTemplateNotFound


class JinjaTemplateRenderer(TemplateRenderer):
    def __init__(self, root: Path | str = Path("app/email_templates")) -> None:
        self._root = Path(root).resolve()
        self._environment = SandboxedEnvironment(
            undefined=StrictUndefined,
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def _template_path(self, template_name: str, template_version: str) -> Path:
        if not template_name.replace("_", "").isalnum():
            raise EmailTemplateNotFound("Email template name is invalid.")
        version_directory = "v" + template_version.split(".", 1)[0]
        candidate = (self._root / "rfq" / version_directory / "template.json").resolve()
        try:
            candidate.relative_to(self._root)
        except ValueError as exc:
            raise EmailTemplateNotFound("Email template path escapes template root.") from exc
        return candidate

    def get_template(self, template_name: str, template_version: str) -> EmailTemplate:
        path = self._template_path(template_name, template_version)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise EmailTemplateNotFound(
                f"Email template {template_name}:{template_version} was not found."
            ) from exc
        if payload.get("name") != template_name or payload.get("version") != template_version:
            raise EmailTemplateNotFound("Email template metadata does not match requested version.")
        return EmailTemplate(
            name=payload["name"],
            version=payload["version"],
            subject_template=payload["subject_template"],
            body_template=payload["body_template"],
            content_type=payload.get("content_type", "text/plain"),
        )

    def render(
        self,
        template_name: str,
        template_version: str,
        context: dict[str, Any],
    ) -> RenderedTemplate:
        template = self.get_template(template_name, template_version)
        try:
            subject = self._environment.from_string(template.subject_template).render(**context)
            body = self._environment.from_string(template.body_template).render(**context)
        except TemplateError as exc:
            raise EmailCompositionError("Unable to render RFQ email template.") from exc
        subject = " ".join(subject.split())
        body = "\n".join(line.rstrip() for line in body.strip().splitlines())
        if not subject or not body:
            raise EmailCompositionError("Rendered RFQ subject or body is empty.")
        return RenderedTemplate(
            subject=subject,
            body=body,
            template_name=template.name,
            template_version=template.version,
            content_type=template.content_type,
        )
