# ADR 0006 — Comparativo determinista de cotizaciones

## Estado

Aceptado para Iteración 14.

## Contexto

`main` ya contenía desde Iteración 9 un `ComparisonRun` con filas JSON, un score fijo 50/35/15 y una recomendación de proveedor. Ese contrato no satisface Iteración 14: el alcance actual termina en un comparativo confiable y prohíbe recomendación automática, scoring avanzado y selección de ganador. Además, el comparador legacy sólo materializa `QuoteItem` existentes y no representa de forma explícita productos no cotizados.

Iteración 13 dejó `Quote`, `QuoteItem`, `QuoteExtractionRun`, `ExtractionArtifact`, evidencia y confidence suficientes para construir el comparativo sin IA adicional.

## Decisión

### Dominio separado

El nuevo agregado vive en `app/domain/comparison` y no depende de FastAPI, SQLAlchemy ni OpenAI.

Se introducen:

- `Comparison`;
- `ComparisonItem` por producto del catálogo aprobado;
- `ComparisonOffer` por proveedor participante;
- `ComparisonWarning` estructurado con severidad `warning` o `critical`;
- value objects `Money`, `Quantity`, `DeliveryTime` y compliance normalizado.

### Persistencia nueva y compatibilidad

No se reinterpretará la tabla legacy `comparison_runs`, porque su semántica incluye scoring y recomendación. Se conserva para historia/compatibilidad y el contrato nuevo usa:

- `comparisons`;
- `comparison_items`;
- `comparison_offers`.

Las ofertas conservan referencias a `Quote`, `QuoteItem` y evidencia. Se snapshottean sólo valores normalizados necesarios para que una comparación ya creada siga siendo reproducible aunque exista una comparación posterior.

### No mutar fuentes por comparar

El comparador v2 no cambia `Quote.approved` a `included_in_comparison` ni muta productos sólo por haber sido comparados. La comparación es una proyección versionada de fuentes aprobadas; ejecutarla no debe alterar la validez de esas fuentes.

### Grid completo

El algoritmo cruza catálogo aprobado × proveedores participantes. La ausencia de un `QuoteItem` se materializa como `OfferStatus.missing`; nunca como precio cero.

Si existen múltiples items actuales del mismo proveedor para el mismo producto, no se elige uno arbitrariamente: la oferta se marca `invalid` con warning crítico `duplicate_quote_item`.

### Normalización determinista

No se usa IA en el comparador.

- Moneda: se conserva el código. No existe FX automático. Monedas distintas producen `requires_normalization`.
- Cantidad/unidad: se normalizan sólo alias lingüísticos seguros. `caja` no se convierte a `pieza` sin equivalencia explícita.
- Entrega: días son comparables. Texto ambiguo se preserva y queda `delivery_normalized=false`.
- Compliance: `unknown` nunca se eleva a `compliant`.

### Criticidad

Warnings como moneda faltante, precio faltante, cantidad/unidad distinta, falta de producto, compliance o entrega desconocida se conservan sin bloquear por defecto el resultado completo.

Son críticos cuando el sistema no puede identificar de forma determinista qué fuente corresponde al catálogo, por ejemplo:

- QuoteItem asociado a producto fuera del snapshot aprobado;
- múltiples QuoteItems actuales del mismo proveedor para el mismo producto.

Si existe al menos un warning crítico el `Comparison.status` termina en `invalid`; de lo contrario en `ready`.

### Versionado e idempotencia

`quotes_version` es SHA-256 de una representación canónica ordenada de las cotizaciones aprobadas: id, versión, hash del archivo y extraction run aprobado.

`comparison_key` es SHA-256 de:

```text
tender_id
+ catalog_snapshot_id:catalog_version
+ quotes_version
+ comparison_rules_version
```

El mismo conjunto de fuentes y reglas devuelve la misma comparación persistida. Un cambio de catálogo, cotización aprobada o versión de reglas produce una nueva identidad.

### API

El contrato v2 utiliza rutas pluralizadas para no confundirlo con el endpoint singular legacy:

- `POST /api/v1/tenders/{tender_id}/comparisons`;
- `GET /api/v1/tenders/{tender_id}/comparisons`;
- `GET /api/v1/comparisons/{comparison_id}`.

La respuesta v2 no contiene score, ranking, ganador ni recomendación.

## Consecuencias

- Se mantiene lectura histórica del comparador de Iteración 9 sin convertir sus datos a una semántica distinta.
- Durante la transición existe deuda explícita: la ruta singular legacy sigue disponible para compatibilidad y debe retirarse en una migración posterior cuando sus consumidores hayan cambiado a v2.
- La comparación v2 es determinista, auditable y puede regenerarse sin costo de IA.
- FX, equivalencias de empaques, scoring, recomendación y award quedan fuera de esta iteración.
