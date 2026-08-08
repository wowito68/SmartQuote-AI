# ADR-0003: Supplier Search Provider

## Context

SmartQuote AI needs supplier discovery without coupling the domain or application use cases to Google, Bing, SerpAPI, HTTP clients, scraping or OpenAI. The repository already contained a `SupplierSearchService` port and a deterministic JSON directory adapter before Iteration 10. No external search API credentials or contracted provider are present in repository configuration.

## Options

1. Keep the local JSON directory as the default adapter.
2. Choose a commercial search API without an existing product decision or credentials.
3. Implement direct web scraping/crawling.

## Decision

Keep `JsonDirectorySearchClient` behind `SearchProviderAdapter` as the real default provider for Iteration 10. The application depends only on `SupplierSearchService`. A dedicated deterministic `SupplierQueryBuilder` now supplies the minimal product query. Public contacts already present in a search result are exposed through `ContactDiscoveryService`; the default contact adapter performs no network request.

## Justification

This extends the architecture already validated in earlier iterations, is fully testable offline, introduces no credential handling, has deterministic behavior and does not invent an external API decision. It also preserves a clean replacement seam for a future business-search provider.

## Costs

The local JSON directory has an external query cost of **USD 0**. The discovery run records provider, query, result count and an estimated external-search cost field so a future provider can report charges without changing domain rules.

## Limitations

- Results are limited to records present in the configured JSON directory.
- There is no live web freshness guarantee.
- There is no crawling, scraping or automatic website enrichment.
- Contacts are never guessed from domains.
- A live provider must be evaluated separately for terms, quotas, pricing, privacy and regional coverage.

## Replacement plan

Implement a new client that satisfies the existing search-provider client contract or a direct `SupplierSearchService` adapter, configure it at the composition edge, and preserve the same request/response DTOs. No domain entity or use case should require modification solely to change providers.
