from pathlib import Path

import pytest

from app.domain.rfqs.exceptions import EmailCompositionError, EmailTemplateNotFound
from app.infrastructure.email.jinja_template_renderer import JinjaTemplateRenderer
from app.infrastructure.email.template_email_composer import TemplateEmailComposer


def valid_context() -> dict:
    return {
        "company": {
            "name": "Compras Industriales",
            "contact_name": "Guillermo Álvarez",
            "email": "compras@example.mx",
            "phone": "+52 442 000 0000",
        },
        "supplier": {"name": "Conductores del Centro"},
        "contact": {"name": "Ana Ventas"},
        "tender": {"id": "tender-1", "title": "Licitación eléctrica"},
        "products": (
            {
                "name": "Cable de cobre",
                "quantity": "2000",
                "unit": "m",
                "description": "Conductor 2 AWG",
                "specifications": {"Tensión": "600 V"},
                "observations": None,
            },
        ),
        "response_deadline": "2026-08-15",
        "observations": "Entrega en Querétaro",
    }


def test_template_renderer_and_composer_are_versioned_and_deterministic() -> None:
    renderer = JinjaTemplateRenderer(Path("app/email_templates"))
    composer = TemplateEmailComposer(renderer)
    first = composer.compose("supplier_rfq", "1.0.0", valid_context())
    second = composer.compose("supplier_rfq", "1.0.0", valid_context())
    assert first == second
    assert "Licitación eléctrica" in first.subject
    assert "Cable de cobre" in first.body
    assert "2000 m" in first.body
    assert first.template_version == "1.0.0"


def test_template_renderer_rejects_unknown_version_and_missing_variables() -> None:
    renderer = JinjaTemplateRenderer(Path("app/email_templates"))
    with pytest.raises(EmailTemplateNotFound):
        renderer.render("supplier_rfq", "9.0.0", valid_context())
    broken = valid_context()
    broken.pop("company")
    with pytest.raises(EmailCompositionError):
        renderer.render("supplier_rfq", "1.0.0", broken)
