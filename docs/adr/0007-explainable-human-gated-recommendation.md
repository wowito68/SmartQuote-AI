# ADR 0007 — Recomendacion explicable y sujeta a revision humana

## Estado

Aceptado para Iteracion 17.

## Contexto

El MVP aprobado termina en el comparativo descriptivo v2. `main` conserva por compatibilidad un comparador legacy de Iteracion 9 con pesos fijos 50/35/15 y una recomendacion embebida. ADR 0006 prohibio reutilizar esa semantica en el comparador v2 y dejo scoring, recomendacion y award como capacidades posteriores.

El comparativo v2 ya materializa una matriz reproducible catalogo aprobado × proveedores participantes, conserva precios, moneda, cantidad/unidad, cumplimiento, entrega, evidencia, confidence y warnings, y no muta sus fuentes.

## Decision

### Agregado separado

La recomendacion se modela como un agregado separado `Recommendation` que referencia un `Comparison` v2 persistido. No modifica las tablas `comparisons`, `comparison_items` o `comparison_offers`, no lee cotizaciones crudas y no reutiliza `ComparisonRun` legacy.

### Pesos explicitos

No existen pesos predeterminados del backend. Cada escenario recibe tres pesos explicitos: cumplimiento tecnico, precio y entrega. Cada peso esta entre 0 y 1 y los tres deben sumar 1. La interfaz inicia los campos vacios y exige una suma de 100% antes de habilitar el calculo.

La version `recommendation_policy_version` versiona las reglas del motor, no los valores elegidos por el usuario.

### Elegibilidad conservadora

Un proveedor debe cubrir todos los productos del comparativo con ofertas validas y cantidad/unidad compatible.

Un criterio con peso mayor que cero exige datos comparables para todos los productos:

- tecnico: `compliant` puntua 1 y `partially_compliant` 0.5; `unknown` no se inventa como valor neutral;
- precio: requiere `MonetaryComparisonStatus.comparable`, total y moneda; no se aplica FX;
- entrega: requiere dias normalizados; texto ambiguo no se convierte automaticamente.

`non_compliant`, oferta faltante/invalida o cantidad no compatible hacen al proveedor inelegible. Un criterio con peso cero no bloquea por ausencia de datos de ese criterio.

### Scoring

Para candidatos elegibles:

- precio relativo = mejor precio comparable / precio del proveedor;
- entrega relativa = menor plazo comparable / plazo del proveedor;
- cumplimiento tecnico se normaliza como 1 o 0.5;
- cada criterio se promedia sobre todos los productos;
- el score total es la suma ponderada y se expresa de 0 a 100.

Los componentes y el score total se persisten para que el resultado sea explicable.

### Retencion de la recomendacion

El resultado tiene dos estados:

- `ready`: existe un unico candidato elegible con el score mas alto;
- `withheld`: no existe candidato elegible o existe empate en el score superior.

Un empate nunca se rompe por UUID, orden de insercion o nombre. `withheld` no contiene proveedor recomendado.

### Revision humana y adjudicacion

Toda recomendacion persiste `human_review_required=true`, reforzado tambien por constraint de base de datos.

Generar una recomendacion no cambia el estado de la licitacion, no transiciona a `awarded`, no selecciona un ganador contractual y no ejecuta compra, negociacion o envio externo.

La adjudicacion futura debe ser una operacion humana separada con su propio contrato y auditoria.

### Idempotencia

`recommendation_key` es SHA-256 de:

```text
comparison_id
+ comparison_key
+ recommendation_policy_version
+ pesos canonicos
```

Repetir el mismo escenario reutiliza el registro. Cambiar cualquier peso o la version de politica crea una nueva identidad sin borrar escenarios anteriores.

### Persistencia y API

Se introduce `recommendations` con FK a `comparisons`, snapshot de pesos, candidatos, scores, exclusiones, explicacion y warnings.

API:

- `POST /api/v1/comparisons/{comparison_id}/recommendations`;
- `GET /api/v1/comparisons/{comparison_id}/recommendations`;
- `GET /api/v1/recommendations/{recommendation_id}`.

## Consecuencias

- La recomendacion es reproducible y no requiere IA adicional.
- No existe costo adicional de OpenAI, busqueda o FX.
- El usuario puede explorar escenarios de pesos distintos sin alterar el comparativo fuente.
- Los datos incompletos producen exclusion o `withheld`, no puntuaciones inventadas.
- El scorer legacy 50/35/15 continua siendo deuda de compatibilidad y no forma parte de este contrato.
- `AWARDED` sigue existiendo en el dominio historico, pero Iteracion 17 no lo utiliza.
