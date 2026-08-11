# Iteración 14 — Validación del comparativo

## Alcance

El comparativo v2 toma exclusivamente fuentes aprobadas y produce una matriz descriptiva. No usa IA, no calcula score, no recomienda proveedor y no selecciona ganador.

## Flujo esperado

```text
CatalogSnapshot aprobado
+ Quote aprobadas
+ QuoteItem actuales
+ proveedores participantes
        ↓
normalización determinista
        ↓
ComparisonBuilder
        ↓
Comparison / ComparisonItem / ComparisonOffer
        ↓
ready | invalid
```

## Casos obligatorios

- misma moneda y precios completos: dimensión monetaria `comparable` cuando existen al menos dos ofertas;
- monedas distintas: `requires_normalization`, sin FX;
- producto no cotizado: oferta `missing`, precio `null`, nunca cero;
- cantidad diferente: warning `quantity_mismatch`;
- unidad diferente: warning `unit_mismatch`, sin conversión implícita;
- compliance `unknown`: permanece unknown;
- entrega desconocida/ambigua: warning y texto original preservado cuando existe;
- item duplicado por producto/proveedor: warning crítico y Comparison `invalid`;
- item asociado fuera del snapshot aprobado: warning crítico y Comparison `invalid`;
- mismo catálogo + mismas quotes + mismas reglas: misma `comparison_key` y mismo registro;
- cambio de reglas/catalog/quote aprobada: nueva identidad de comparación.

## Persistencia

La migración `b7e2f94c5d83` debe pasar:

```text
alembic upgrade head
alembic downgrade base
alembic upgrade head
```

Se verifica que `comparison_offers` se elimina antes de `comparison_items` y `comparisons` en cleanup/downgrade para respetar FKs.

## API

Se validan en OpenAPI:

- `POST /api/v1/tenders/{tender_id}/comparisons`;
- `GET /api/v1/tenders/{tender_id}/comparisons`;
- `GET /api/v1/comparisons/{comparison_id}`.

El schema `ComparisonResponseSchema` no debe contener `score` ni `recommendation`.

## Auditoría

Eventos v2:

- `comparison.created`;
- `comparison.ready`;
- `comparison.invalid`.

El evento histórico `RecommendationGenerated` no forma parte del flujo v2.

## Compatibilidad conocida

El endpoint singular de Iteración 9 (`/tenders/{id}/comparison`) y la tabla `comparison_runs` permanecen temporalmente por compatibilidad. Son legacy y no son utilizados por el módulo v2.

## Gate de CI

`.github/workflows/iteration-14-comparison.yml` ejecuta:

- Ruff del código nuevo;
- ciclo limpio de migración PostgreSQL;
- unit tests del normalizador/builder;
- integration test de API/persistencia/idempotencia/auditoría;
- contrato OpenAPI;
- build frontend.
