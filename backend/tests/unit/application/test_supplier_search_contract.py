from uuid import uuid4

from app.application.ports.supplier_search_service import (
    SupplierSearchProduct,
    SupplierSearchRequest,
)
from app.infrastructure.search.search_provider_adapter import (
    SearchProviderAdapter,
    SearchProviderRecord,
)


class FakeSearchProviderClient:
    provider_name = "fake-provider"
    provider_version = "contract-1"

    def __init__(self) -> None:
        self.queries: list[str] = []

    def search(self, *, query: str, category: str | None, country: str | None, max_results: int):
        self.queries.append(query)
        return (
            SearchProviderRecord(
                legal_name="Proveedor Uno SA",
                trade_name="Proveedor Uno",
                website="https://proveedor.example",
                category=category,
                country=country,
                city="Querétaro",
                description="Distribuidor industrial",
                source_url="https://directory.example/proveedor-uno",
                source_title="Directorio de proveedores",
                metadata={"directory_score": 0.72},
            ),
        )


def test_supplier_search_port_adapter_preserves_query_provider_and_score() -> None:
    client = FakeSearchProviderClient()
    adapter = SearchProviderAdapter(client)
    request = SupplierSearchRequest(
        tender_id=uuid4(),
        product=SupplierSearchProduct(
            product_id=uuid4(),
            name="Sensor industrial",
            description=None,
            category="Instrumentación",
            specifications={"salida": "4-20mA"},
        ),
        country="MX",
        max_results=5,
        query="sensor industrial 4-20mA MX",
        query_version="1.0.0",
    )

    response = adapter.search(request)

    assert client.queries == ["sensor industrial 4-20mA MX"]
    assert adapter.provider_name == "fake-provider"
    assert response.estimated_cost_usd == 0.0
    assert len(response.suggestions) == 1
    suggestion = response.suggestions[0]
    assert suggestion.query == request.query
    assert suggestion.search_provider == "fake-provider"
    assert suggestion.initial_score == 0.72
    assert suggestion.searched_at is not None
