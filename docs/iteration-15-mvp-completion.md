# Iteración 15 — Cierre y hardening del MVP

## Diagnóstico

La Iteración 14 dejó implementado el comparativo determinista v2 en backend, pero el MVP todavía tenía dos brechas operativas:

1. el frontend no exponía el comparativo, por lo que el flujo completo no podía probarse desde la UI;
2. el gate global de cobertura permanecía por debajo del 90% aunque el full test suite pasaba.

El backend ya sincronizaba la licitación a `comparison_ready` cuando un comparativo quedaba `ready`, por lo que esa lógica se reutiliza sin duplicarla.

La recomendación automática no forma parte de esta iteración. El alcance aprobado del MVP termina en el comparativo básico.

## Implementación

### Frontend

Se añadió `frontend/src/features/comparison/` con:

- tipos TypeScript alineados al contrato v2;
- cliente HTTP para generar y consultar comparativos;
- `ComparisonPanel`;
- navegación `Comparativo`.

La matriz muestra:

- producto solicitado;
- cantidad/unidad solicitada;
- proveedor;
- producto cotizado;
- marca/modelo;
- cantidad y estado frente a la solicitud;
- precio unitario y total;
- moneda;
- cumplimiento;
- entrega;
- condiciones comerciales;
- observaciones;
- disponibilidad de evidencia;
- confidence;
- warnings estructurados.

Un producto no cotizado se muestra como `No cotizado`; precio y cantidad permanecen nulos. La interfaz no calcula FX, ranking, score ni recomendación.

### Hardening de dominio

La Iteración 15 no modifica reglas productivas para incrementar cobertura. Se añadieron pruebas sobre invariantes ya existentes:

- `Quote`, `QuoteDocument`, `QuoteExtractionRun`, `QuoteItem`, `QuoteTaskRecord`;
- RFQ, snapshots, mensajes de email, task records y outbound logs;
- Supplier, contactos, fuentes, `TenderSupplier`, descubrimiento, matching y merge suggestions;
- procesamiento documental;
- entidades y lifecycle de `Comparison`.

Las pruebas ejercitan transiciones válidas e inválidas, reintentos, fallos, aprobación/inmutabilidad, normalización, duplicados y serialización.

## Persistencia y migraciones

No se añade una migración Alembic en esta iteración porque no cambia el modelo persistente. El esquema de comparación de Iteración 14 se reutiliza sin modificaciones.

El gate de Iteración 15 aplica las migraciones existentes sobre PostgreSQL antes de ejecutar la suite completa.

## CI

Se añadió `.github/workflows/iteration-15-mvp-completion.yml` con dos jobs:

### Backend MVP quality gate

- Python 3.12;
- PostgreSQL 16;
- Redis 7;
- instalación locked con uv;
- Ruff global;
- `alembic upgrade head`;
- full pytest con coverage;
- reporte de líneas faltantes;
- threshold global mínimo del 90%.

El threshold no se reduce para aprobar la iteración.

### Frontend MVP build

- Node 22;
- `npm ci`;
- build de producción.

## Decisiones

- No se introduce una segunda implementación de comparación.
- No se modifica `ComparisonBuilder` sólo para facilitar la UI.
- No se añade Celery al comparativo porque es una operación determinista/transaccional rápida.
- No se crea una migración vacía.
- No se implementa recomendación automática.
- El comparador legacy de Iteración 9 permanece como deuda de compatibilidad documentada por ADR 0006; la UI nueva consume únicamente el contrato v2 pluralizado.

## Criterios de cierre

La iteración sólo puede marcarse completa cuando el SHA final cumpla simultáneamente:

- frontend production build verde;
- Ruff global verde;
- migraciones PostgreSQL verdes;
- full pytest verde;
- cobertura global >= 90%;
- workflows regresivos relevantes verdes;
- documentación actualizada.

Los resultados exactos deben registrarse en el PR/final report después de ejecutarse sobre el SHA final.

## Fuera de alcance

- recomendación automática;
- ranking/scoring avanzado;
- proveedor ganador;
- conversión FX;
- ERP/compras;
- negociación automática;
- OCR completo;
- agentes autónomos;
- microservicios.
