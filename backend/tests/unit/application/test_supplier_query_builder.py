from uuid import uuid4

from app.application.ports.supplier_search_service import SupplierSearchProduct
from app.application.services.supplier_query_builder import SupplierQueryBuilder


def test_supplier_query_builder_is_deterministic_and_uses_minimal_product_data() -> None:
    product = SupplierSearchProduct(
        product_id=uuid4(),
        name="Sensor de temperatura industrial",
        description="Sensor para proceso industrial con transmisor integrado y montaje en campo.",
        category="Instrumentación",
        specifications={
            "protección": "IP67",
            "salida": "4-20mA",
            "alimentación": "24V",
            "rango": "-20 a 120 °C",
            "marca": "Acme",
            "modelo": "TX-120",
        },
    )
    builder = SupplierQueryBuilder("1.0.0", max_description_chars=0)

    first = builder.build(product, country="México")
    second = builder.build(product, country="México")

    assert first == second
    assert first.version == "1.0.0"
    assert first.text.startswith("Sensor de temperatura industrial Acme TX-120")
    assert "4-20mA" in first.text
    assert "24V" in first.text
    assert "IP67" in first.text
    assert first.text.endswith("Instrumentación México")


def test_supplier_query_builder_has_a_bounded_payload() -> None:
    product = SupplierSearchProduct(
        product_id=uuid4(),
        name="Cable industrial",
        description="x" * 2000,
        category="Eléctrico",
        specifications={f"k{index}": f"v{index}" for index in range(30)},
    )
    result = SupplierQueryBuilder(
        max_specifications=3,
        max_description_chars=20,
        max_query_chars=120,
    ).build(product, country="MX")

    assert len(result.text) <= 120
    assert "v0" in result.text
    assert "v3" not in result.text
