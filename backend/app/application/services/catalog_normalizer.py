import hashlib
import json
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass(frozen=True, slots=True)
class NormalizedCatalogItem:
    name: str
    description: str | None
    quantity: Decimal | None
    unit: str | None
    category: str | None
    specifications: dict[str, str]
    observations: str | None
    fingerprint: str


class CatalogNormalizer:
    UNIT_ALIASES = {
        "pieza": "pieza",
        "piezas": "pieza",
        "pza": "pieza",
        "pzas": "pieza",
        "unidad": "pieza",
        "unidades": "pieza",
        "ud": "pieza",
        "kg": "kg",
        "kilogramo": "kg",
        "kilogramos": "kg",
        "g": "g",
        "gramo": "g",
        "gramos": "g",
        "l": "L",
        "lt": "L",
        "litro": "L",
        "litros": "L",
        "ml": "mL",
        "mililitro": "mL",
        "mililitros": "mL",
        "m": "m",
        "metro": "m",
        "metros": "m",
        "cm": "cm",
        "mm": "mm",
        "caja": "caja",
        "cajas": "caja",
        "paquete": "paquete",
        "paquetes": "paquete",
        "juego": "juego",
        "juegos": "juego",
        "servicio": "servicio",
        "servicios": "servicio",
    }
    CATEGORY_RULES = (
        (("cable", "conductor", "terminal", "interruptor", "transformador"), "Eléctrico"),
        (("tornillo", "tuerca", "perno", "arandela", "herramienta"), "Ferretería"),
        (("computadora", "laptop", "servidor", "monitor", "impresora"), "Tecnología"),
        (("casco", "guante", "protección", "chaleco", "respirador"), "Seguridad industrial"),
        (("válvula", "tubería", "bomba", "brida", "conexión"), "Hidráulico"),
    )

    @staticmethod
    def clean_text(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = re.sub(r"\s+", " ", value).strip()
        return normalized or None

    def normalize_unit(self, unit: str | None) -> str | None:
        cleaned = self.clean_text(unit)
        if cleaned is None:
            return None
        key = cleaned.casefold().rstrip(".")
        return self.UNIT_ALIASES.get(key, cleaned)

    def normalize_quantity(
        self, quantity: Decimal | None, unit: str | None
    ) -> tuple[Decimal | None, str | None]:
        normalized_unit = self.normalize_unit(unit)
        if quantity is None:
            return None, normalized_unit
        value = Decimal(quantity)
        if normalized_unit == "g" and value >= 1000:
            return value / Decimal("1000"), "kg"
        if normalized_unit == "mL" and value >= 1000:
            return value / Decimal("1000"), "L"
        if normalized_unit == "cm" and value >= 100:
            return value / Decimal("100"), "m"
        if normalized_unit == "mm" and value >= 1000:
            return value / Decimal("1000"), "m"
        return value.normalize(), normalized_unit

    def suggest_category(self, name: str, description: str | None) -> str | None:
        haystack = f"{name} {description or ''}".casefold()
        for keywords, category in self.CATEGORY_RULES:
            if any(keyword in haystack for keyword in keywords):
                return category
        return None

    def normalize(
        self,
        *,
        name: str,
        description: str | None,
        quantity: Decimal | None,
        unit: str | None,
        category: str | None,
        specifications: dict[str, str],
        observations: str | None,
    ) -> NormalizedCatalogItem:
        normalized_name = self.clean_text(name) or ""
        normalized_description = self.clean_text(description)
        normalized_quantity, normalized_unit = self.normalize_quantity(quantity, unit)
        normalized_specs = {
            self.clean_text(key) or "": self.clean_text(value) or ""
            for key, value in specifications.items()
            if self.clean_text(key) and self.clean_text(value)
        }
        normalized_category = self.clean_text(category) or self.suggest_category(
            normalized_name, normalized_description
        )
        normalized_observations = self.clean_text(observations)
        fingerprint_payload: dict[str, Any] = {
            "name": normalized_name.casefold(),
            "unit": normalized_unit,
            "category": normalized_category,
            "specifications": sorted(normalized_specs.items()),
        }
        fingerprint = hashlib.sha256(
            json.dumps(fingerprint_payload, ensure_ascii=False, sort_keys=True).encode()
        ).hexdigest()
        return NormalizedCatalogItem(
            name=normalized_name,
            description=normalized_description,
            quantity=normalized_quantity,
            unit=normalized_unit,
            category=normalized_category,
            specifications=normalized_specs,
            observations=normalized_observations,
            fingerprint=fingerprint,
        )
