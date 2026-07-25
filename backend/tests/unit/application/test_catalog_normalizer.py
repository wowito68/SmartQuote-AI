from decimal import Decimal

from app.application.services.catalog_normalizer import CatalogNormalizer


def test_catalog_normalizer_cleans_units_converts_and_suggests_category() -> None:
    normalized = CatalogNormalizer().normalize(
        name="  Cable   de cobre  ",
        description=" conductor   para instalación ",
        quantity=Decimal("2000"),
        unit=" metros ",
        category=None,
        specifications={" Calibre ": " 2 AWG ", "": "ignored"},
        observations=" entrega inmediata ",
    )
    assert normalized.name == "Cable de cobre"
    assert normalized.quantity == Decimal("2000")
    assert normalized.unit == "m"
    assert normalized.category == "Eléctrico"
    assert normalized.specifications == {"Calibre": "2 AWG"}


def test_catalog_normalizer_converts_mass_volume_and_detects_same_fingerprint() -> None:
    normalizer = CatalogNormalizer()
    first = normalizer.normalize(
        name="Reactivo",
        description=None,
        quantity=Decimal("2500"),
        unit="gramos",
        category="Laboratorio",
        specifications={"Pureza": "99 %"},
        observations=None,
    )
    second = normalizer.normalize(
        name=" Reactivo ",
        description="different description",
        quantity=Decimal("2.5"),
        unit="kg",
        category="Laboratorio",
        specifications={"Pureza": "99 %"},
        observations="other",
    )
    assert first.quantity == Decimal("2.5")
    assert first.unit == "kg"
    assert first.fingerprint == second.fingerprint


def test_unknown_unit_and_category_are_preserved() -> None:
    item = CatalogNormalizer().normalize(
        name="Producto especial",
        description=None,
        quantity=Decimal("3"),
        unit="rollo",
        category="Especial",
        specifications={},
        observations=None,
    )
    assert item.unit == "rollo"
    assert item.category == "Especial"
