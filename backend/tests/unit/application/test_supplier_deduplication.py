from app.application.ports.supplier_search_service import (
    SupplierContactSuggestion,
    SupplierSuggestion,
)
from app.application.services.supplier_deduplication import SupplierDeduplicationService
from app.domain.suppliers.entities import Supplier, SupplierContact
from app.domain.suppliers.value_objects import SupplierConfidence, SupplierContactType


def suggestion(**changes) -> SupplierSuggestion:
    values = {
        "legal_name": "Conductores del Centro SA de CV",
        "trade_name": "Conductores Centro",
        "website": "https://conductores.example.mx",
        "category": "Eléctrico",
        "country": "MX",
        "city": "Querétaro",
        "description": "Fabricante de conductores",
        "source_url": "https://directory.example.mx/1",
        "contacts": (
            SupplierContactSuggestion(
                contact_type="email",
                value="ventas@conductores.example.mx",
                confidence=0.9,
                source_url="https://conductores.example.mx/contacto",
            ),
        ),
    }
    values.update(changes)
    return SupplierSuggestion(**values)


def test_deduplication_recognizes_exact_domain_identity() -> None:
    supplier = Supplier(
        legal_name="Conductores Centro, S.A. de C.V.",
        website="https://www.conductores.example.mx/catalogo",
    )
    result = SupplierDeduplicationService().compare(suggestion(), supplier, [])
    assert result.exact_identity is True
    assert "same_web_domain" in result.signals
    assert result.score >= 0.6


def test_deduplication_generates_partial_merge_signal_without_auto_identity() -> None:
    supplier = Supplier(
        legal_name="Conductores del Centro Industrial SA",
        trade_name="Conductores Centro Industrial",
        website="https://otro-dominio.example.mx",
    )
    result = SupplierDeduplicationService().compare(
        suggestion(website="https://conductores-nuevo.example.mx", contacts=()),
        supplier,
        [],
    )
    assert result.exact_identity is False
    assert result.score >= SupplierDeduplicationService.suggestion_threshold
    assert any(signal.startswith("legal_name_similarity") for signal in result.signals)


def test_deduplication_uses_email_and_phone_evidence() -> None:
    supplier = Supplier(trade_name="Distribuidora Técnica")
    contacts = [
        SupplierContact(
            supplier_id=supplier.id,
            contact_type=SupplierContactType.EMAIL,
            value="ventas@distribuidora.mx",
            confidence=SupplierConfidence(1),
            source_url="https://distribuidora.mx",
        ),
        SupplierContact(
            supplier_id=supplier.id,
            contact_type=SupplierContactType.PHONE,
            value="+52 442 123 4567",
            confidence=SupplierConfidence(1),
            source_url="https://distribuidora.mx",
        ),
    ]
    result = SupplierDeduplicationService().compare(
        suggestion(
            legal_name=None,
            trade_name="Distribuidora Tecnica",
            website=None,
            contacts=(
                SupplierContactSuggestion(
                    contact_type="email",
                    value="ventas@distribuidora.mx",
                    confidence=0.7,
                    source_url="https://source.mx",
                ),
                SupplierContactSuggestion(
                    contact_type="phone",
                    value="4421234567",
                    confidence=0.7,
                    source_url="https://source.mx",
                ),
            ),
        ),
        supplier,
        contacts,
    )
    assert {"same_email", "same_phone"}.issubset(result.signals)
    assert result.exact_identity is True
