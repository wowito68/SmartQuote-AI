from app.application.ports.supplier_search_service import SupplierSuggestion
from app.application.services.supplier_deduplication import (
    SupplierDeduplicationService,
    SupplierDuplicateStatus,
)
from app.domain.suppliers.entities import Supplier


def _suggestion(**overrides) -> SupplierSuggestion:
    values = {
        "legal_name": "Industrias del Norte, S.A. de C.V.",
        "trade_name": "Industrias Norte",
        "website": "https://candidate.example",
        "category": "Industrial",
        "country": "MX",
        "city": "Monterrey",
        "description": "Suministros industriales",
        "source_url": "https://directory.example/candidate",
    }
    values.update(overrides)
    return SupplierSuggestion(**values)


def test_strong_domain_signal_is_an_exact_duplicate() -> None:
    supplier = Supplier(
        legal_name="Otra razón social",
        website="https://www.candidate.example/catalogo",
    )
    result = SupplierDeduplicationService().compare(_suggestion(), supplier, [])

    assert result.status is SupplierDuplicateStatus.DUPLICATE
    assert result.exact_identity is True
    assert "same_web_domain" in result.signals


def test_similar_names_without_strong_identity_are_possible_duplicate() -> None:
    supplier = Supplier(
        legal_name="Industrias del Norte SA de CV",
        trade_name="Industrias Norte México",
        website="https://other.example",
        city="Monterrey",
    )
    result = SupplierDeduplicationService().compare(_suggestion(), supplier, [])

    assert result.status is SupplierDuplicateStatus.POSSIBLE_DUPLICATE
    assert result.exact_identity is False
    assert result.score >= 0.4


def test_unrelated_supplier_is_unique() -> None:
    supplier = Supplier(
        legal_name="Servicios del Pacífico",
        trade_name="Pacífico",
        website="https://pacifico.example",
        city="Tijuana",
    )
    result = SupplierDeduplicationService().compare(_suggestion(), supplier, [])

    assert result.status is SupplierDuplicateStatus.UNIQUE
    assert result.exact_identity is False
