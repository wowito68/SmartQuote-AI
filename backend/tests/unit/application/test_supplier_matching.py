from app.application.services.supplier_matching import SupplierMatchingService
from app.domain.suppliers.entities import Supplier


def test_supplier_matching_is_deterministic_and_explains_score() -> None:
    service = SupplierMatchingService()
    product = {
        "name": "Cable de cobre 2 AWG",
        "description": "Conductor con aislamiento XLPE para 600 V",
        "category": "Eléctrico",
        "specifications": {"Calibre": "2 AWG", "Tensión": "600 V"},
    }
    supplier = Supplier(
        trade_name="Conductores Centro",
        category="Eléctrico",
        description="Fabricante de cable de cobre XLPE 2 AWG para 600 V",
    )
    first = service.calculate(product, supplier)
    second = service.calculate(product, supplier)
    assert first == second
    assert first.score >= 40
    assert set(first.components) == {"name", "category", "keywords", "specifications"}
    assert len(first.reasons) == 4


def test_supplier_matching_penalizes_unrelated_supplier() -> None:
    result = SupplierMatchingService().calculate(
        {
            "name": "Cable de cobre",
            "description": None,
            "category": "Eléctrico",
            "specifications": {},
        },
        Supplier(
            trade_name="Servicios de Limpieza",
            category="Limpieza",
            description="Productos de higiene institucional",
        ),
    )
    assert result.score < 10
