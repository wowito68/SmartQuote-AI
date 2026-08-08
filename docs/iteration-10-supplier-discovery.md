# Iteration 10 - Supplier discovery and management

## Scope implemented

Iteration 10 hardens the supplier module that already existed after Iteration 9. It does not replace the modular monolith or Clean Architecture. The flow is:

`approved catalog -> deterministic query -> SupplierSearchService -> candidate -> normalization -> deduplication -> sources -> public contacts -> deterministic product match -> human review -> approved/rejected supplier -> confirmed product association -> RFQ eligibility`

No automatic RFQ email is sent by this discovery flow.

## Architecture

Application ports remain provider-agnostic:

- `SupplierSearchService`: supplier candidate search.
- `ContactDiscoveryService`: public contact data already provided by an allowed source.
- `SupplierDiscoveryQueue`: asynchronous execution.

Default adapters:

- `SearchProviderAdapter(JsonDirectorySearchClient)`: local JSON directory.
- `InlineContactDiscoveryService`: reuses source-provided public contacts and performs no scraping or network calls.
- Celery: asynchronous supplier discovery with retry on search failures.

## Deterministic query builder

`SupplierQueryBuilder` uses only approved product fields needed for discovery: name, bounded description, category, a bounded number of specifications, brand/model when represented in specifications, optional keywords, city and country. It does not send the complete tender document and does not use AI.

Query behavior is versioned through `SMARTQUOTE_SUPPLIER_SEARCH_QUERY_VERSION`.

## Normalization and deduplication

The original business values remain stored. Candidate normalization separately canonicalizes name, domain, HTTP(S) URL, email, phone, country and city for comparison.

Deduplication exposes three explicit outcomes:

- `duplicate`: a strong identity such as same domain, corporate email, phone or normalized legal identity.
- `possible_duplicate`: weak signals cross the review threshold but do not justify automatic merge.
- `unique`: no sufficient duplicate evidence.

Possible duplicates create merge suggestions for human review. They are never silently merged.

## Product-to-supplier scoring

The baseline is deterministic and centralized in `SupplierMatchingWeights`:

- product/name overlap: 35 points;
- category overlap: 25 points;
- general keyword overlap: 20 points;
- specification overlap: 20 points.

Brand/model contribute through specification overlap when supplied as product specifications. Every match stores component scores and human-readable reasons. A confirmed association requires both an approved product and an approved tender supplier.

## Idempotency and refresh

A logical supplier search identity includes the tender, approved catalog version/snapshot, search provider/version, query version, deduplication version, matching version, contact provider/version and search criteria.

Without `refresh`, a completed identical search is reused. With `refresh=true`, a new execution is created with a monotonically increasing refresh sequence and a link to the previous run. Historical sources and candidates are retained instead of overwritten.

## Traceability

Each automatic source can record:

- supplier;
- discovery run;
- product;
- source type, URL and name;
- query;
- provider;
- discovery timestamp;
- search metadata, score and estimated cost.

Discovery runs also retain a correlation ID. Approval/rejection continues to record the reviewing user through the existing supplier aggregate.

## API

Existing routes remain compatible. Iteration 10 adds or extends:

- `POST /api/v1/tenders/{tender_id}/suppliers/discover` - accepts `refresh` and optional `correlation_id`.
- `GET /api/v1/tenders/{tender_id}/supplier-candidates` - historical candidate/search trace.
- `GET /api/v1/tenders/{tender_id}/suppliers` - existing supplier review view with richer sources/matches.
- `GET /api/v1/suppliers/{supplier_id}` - existing supplier detail.
- `POST /api/v1/suppliers/{supplier_id}/approve` - existing human approval.
- `POST /api/v1/suppliers/{supplier_id}/reject` - existing human rejection.
- `GET /api/v1/products/{product_id}/suppliers` - explainable matches for a product.
- `POST /api/v1/products/{product_id}/suppliers/{supplier_id}/match` - confirm association; requires approved product and supplier.

## Configuration

Environment variables:

- `SMARTQUOTE_SUPPLIER_DIRECTORY_PATH`
- `SMARTQUOTE_SUPPLIER_SEARCH_COUNTRY`
- `SMARTQUOTE_SUPPLIER_SEARCH_CITY`
- `SMARTQUOTE_SUPPLIER_SEARCH_QUERY_VERSION`
- `SMARTQUOTE_SUPPLIER_SEARCH_MAX_RESULTS_PER_PRODUCT`
- `SMARTQUOTE_SUPPLIER_MATCHING_ALGORITHM_VERSION`

No supplier-search API key is required for the current JSON-directory provider.

## Security constraints

Automatically discovered source URLs must be HTTP(S). URLs containing embedded credentials are rejected by normalization. Discovery does not execute external code, download supplier files, crawl websites, infer emails, or treat external content as system instructions.

## Explicit exclusions

No mass scraping/crawling, autonomous agents, negotiation, automatic RFQ sending, inbox automation, OCR, ERP, multi-tenancy, microservices, ML scoring, vector database or supplier RAG is introduced in Iteration 10.
