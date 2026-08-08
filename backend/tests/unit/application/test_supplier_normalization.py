from uuid import uuid4

from app.application.ports.supplier_search_service import (
    SupplierContactSuggestion,
    SupplierSuggestion,
)
from app.application.services.supplier_normalization import (
    SupplierCandidateNormalizer,
    normalize_domain,
    normalize_http_url,
    normalize_name,
)


def test_supplier_normalization_preserves_original_and_canonicalizes_identity() -> None:
    suggestion = SupplierSuggestion(
        legal_name="Comercializadora Águila, S.A. de C.V.",
        trade_name="Águila Industrial",
        website="http://www.Example.COM/catalogo/",
        category="Industrial",
        country="MX",
        city="Querétaro",
        description=None,
        source_url="https://directory.example/company",
        contacts=(
            SupplierContactSuggestion(
                contact_type="email",
                value="VENTAS@EXAMPLE.COM",
                confidence=0.9,
                source_url="https://example.com/contacto",
            ),
            SupplierContactSuggestion(
                contact_type="phone",
                value="+52 442 123 4567",
                confidence=0.8,
                source_url="https://example.com/contacto",
            ),
        ),
    )

    normalized = SupplierCandidateNormalizer().normalize(suggestion)

    assert normalized.original_name == "Águila Industrial"
    assert normalized.normalized_name == "aguila industrial"
    assert normalized.normalized_domain == "example.com"
    assert normalized.normalized_url == "https://example.com/catalogo"
    assert normalized.normalized_emails == ("ventas@example.com",)
    assert normalized.normalized_phones == ("4421234567",)
    assert suggestion.website == "http://www.Example.COM/catalogo/"


def test_url_normalization_rejects_credentials_and_non_http_schemes() -> None:
    assert normalize_domain("https://www.example.com") == "example.com"
    assert normalize_http_url("https://user:secret@example.com") is None
    assert normalize_http_url("javascript:alert(1)") is None
    assert normalize_name("  ACME, S.A.  ") == "acme s a"
