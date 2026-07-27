from uuid import uuid4

import pytest

from app.domain.shared.exceptions import ValidationError
from app.domain.suppliers.entities import (
    Supplier,
    SupplierContact,
    SupplierMergeSuggestion,
    TenderSupplier,
)
from app.domain.suppliers.exceptions import InvalidSupplierState, SupplierMergeConflict
from app.domain.suppliers.value_objects import (
    SupplierConfidence,
    SupplierContactType,
    SupplierStatus,
)


def test_supplier_normalizes_domain_and_requires_a_name() -> None:
    supplier = Supplier(
        legal_name="  Conductores   del Centro SA de CV ",
        website="https://www.Conductores.Example.MX/catalogo",
    )
    assert supplier.legal_name == "Conductores del Centro SA de CV"
    assert supplier.normalized_domain == "conductores.example.mx"
    with pytest.raises(ValidationError):
        Supplier()


def test_tender_supplier_enforces_review_transitions() -> None:
    item = TenderSupplier(tender_id=uuid4(), supplier_id=uuid4())
    with pytest.raises(InvalidSupplierState):
        item.approve(uuid4())
    item.mark_contact_discovery_complete()
    item.start_review()
    item.approve(uuid4())
    assert item.status is SupplierStatus.APPROVED
    with pytest.raises(InvalidSupplierState):
        item.reject(uuid4(), "late rejection")


def test_supplier_contact_validates_type_and_builds_identity_key() -> None:
    contact = SupplierContact(
        supplier_id=uuid4(),
        contact_type=SupplierContactType.EMAIL,
        value="VENTAS@Example.MX",
        confidence=SupplierConfidence(0.91),
        source_url="https://example.mx/contacto",
    )
    assert contact.identity_key == "email:ventas@example.mx"
    with pytest.raises(ValidationError):
        SupplierContact(
            supplier_id=uuid4(),
            contact_type=SupplierContactType.PHONE,
            value="123",
            confidence=SupplierConfidence(0.5),
            source_url="https://example.mx",
        )


def test_merge_suggestion_and_supplier_merge_are_reviewed() -> None:
    source = Supplier(trade_name="Proveedor Uno")
    target = Supplier(trade_name="Proveedor Dos")
    suggestion = SupplierMergeSuggestion(
        source_supplier_id=source.id,
        target_supplier_id=target.id,
        score=SupplierConfidence(0.72),
        signals=("trade_name_similarity:0.900",),
    )
    reviewer = uuid4()
    suggestion.accept(reviewer)
    source.merge_into(target.id)
    assert source.merged_into_supplier_id == target.id
    with pytest.raises(SupplierMergeConflict):
        source.merge_into(uuid4())
