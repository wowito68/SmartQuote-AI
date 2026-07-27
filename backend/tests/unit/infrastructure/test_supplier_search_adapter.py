import json
from pathlib import Path
from uuid import uuid4

from app.application.ports.supplier_search_service import (
    SupplierSearchProduct,
    SupplierSearchRequest,
)
from app.infrastructure.search.search_provider_adapter import (
    JsonDirectorySearchClient,
    SearchProviderAdapter,
)


def test_json_search_adapter_returns_structured_sources_and_contacts(tmp_path: Path) -> None:
    directory = tmp_path / "suppliers.json"
    directory.write_text(
        json.dumps(
            {
                "suppliers": [
                    {
                        "legal_name": "Conductores del Centro SA de CV",
                        "trade_name": "Conductores Centro",
                        "website": "https://conductores.example.mx",
                        "category": "Eléctrico",
                        "country": "MX",
                        "city": "Querétaro",
                        "description": "Cable de cobre XLPE 2 AWG",
                        "keywords": ["cable", "cobre", "XLPE"],
                        "source_url": "https://directory.example.mx/conductores",
                        "contacts": [
                            {
                                "contact_type": "email",
                                "value": "ventas@conductores.example.mx",
                                "confidence": 0.9,
                                "source_url": "https://conductores.example.mx/contacto",
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    adapter = SearchProviderAdapter(JsonDirectorySearchClient(directory))
    response = adapter.search(
        SupplierSearchRequest(
            tender_id=uuid4(),
            product=SupplierSearchProduct(
                product_id=uuid4(),
                name="Cable de cobre",
                description="Aislamiento XLPE",
                category="Eléctrico",
                specifications={"Calibre": "2 AWG"},
            ),
            country="MX",
            max_results=5,
        )
    )
    assert adapter.provider_name == "json-directory"
    assert len(response.suggestions) == 1
    assert response.suggestions[0].source_url.startswith("https://directory")
    assert response.suggestions[0].contacts[0].value.startswith("ventas@")
