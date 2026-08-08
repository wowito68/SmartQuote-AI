# Iteración 9 — MVP end-to-end de cotizaciones

## Alcance real

La Iteración 9 extiende el monolito modular existente. No recrea licitaciones, documentos, catálogo, proveedores ni RFQ: consume los puertos, repositorios, almacenamiento, auditoría, proveedor IA y Celery ya implementados.

El tramo nuevo es:

```text
RFQ enviado
  -> carga manual de cotización PDF
  -> validación/hash/almacenamiento privado
  -> extracción de texto
  -> extracción IA versionada
  -> Quote + QuoteItems normalizados
  -> revisión humana
  -> cotización aprobada
  -> comparativo determinista
  -> recomendación explicable para revisión humana
```

## Arquitectura

- Dominio: `app/domain/quotes`, `app/domain/comparisons`.
- Casos de uso: `app/application/use_cases/quotes.py`.
- Puertos: `QuoteRepository`, `QuoteAnalysisQueue` y puertos existentes de storage, extracción de texto, prompt registry e IA.
- Persistencia: SQLAlchemy en `app/infrastructure/db/models/quote.py` y `repositories/quote_repository.py`.
- Asíncrono: `smartquote.quotes.analyze` en la cola `quote-analysis`.
- API: `app/api/routes/quotes.py`.
- Prompt: `app/prompts/quote_extraction/v1/prompt.json`.
- Migración: `c9e5f10a7b43_quote_comparison_mvp.py`.

## Estados

### Tender

```text
draft
-> documents_pending
-> documents_processing
-> catalog_review
-> supplier_review
-> rfq_ready
-> waiting_quotes
-> quote_analysis
-> comparison_ready
-> awarded / closed / cancelled
```

No se permiten saltos arbitrarios. `awarded` únicamente puede avanzar a `closed`.

### Quote

```text
received
-> validating
-> extracting
-> extracted
-> normalized
-> pending_review
-> approved / rejected
approved -> included_in_comparison
```

La aprobación o rechazo solo es válido desde `pending_review`.

### Estados extendidos

- Product: `quoted`, `compared` después de `approved`.
- Supplier: `contacted`, `responded`, `inactive` después del ciclo de revisión.
- RFQ: `responded` después de `sent/delivered`.

## Idempotencia

### Carga de cotización

Restricción única:

```text
tender_id + supplier_id + file_hash
```

El `file_hash` es SHA-256 del PDF validado.

### Extracción de cotización

La clave SHA-256 incluye:

```text
file_hash
+ tender_id
+ supplier_id
+ extractor_version
+ prompt_version
+ model
+ schema_hash
```

Un run completado con items persistidos se reutiliza. Un run fallido se puede reiniciar de forma segura.

### Comparativo

La clave SHA-256 incluye:

```text
tender_id
+ approved_catalog_snapshot_id
+ approved_catalog_version
+ approved_quotes_version
+ scoring_config_version
```

La versión de cotizaciones aprobadas se deriva de `quote_id + quote.version + file_hash` de cada cotización participante.

## Trazabilidad IA

`QuoteExtractionRun` registra:

- `quote_id`, `tender_id`, `supplier_id`;
- extractor y versión;
- prompt y versión;
- modelo;
- schema version/hash;
- tokens de entrada/salida;
- costo estimado USD;
- provider response id;
- respuesta estructurada;
- estado, inicio, término y error.

Cada `QuoteItem` conserva:

- página fuente;
- fragmento de evidencia;
- confianza;
- asociación opcional al producto de catálogo.

El fragmento de evidencia debe existir literalmente en la página indicada antes de aceptar el resultado del proveedor IA.

## Normalización

El matching con el catálogo aprobado es deliberadamente conservador:

1. coincidencia exacta de nombre normalizado;
2. si no existe exacta, se acepta únicamente una coincidencia parcial única;
3. si hay ambigüedad, `catalog_product_id` permanece `null`.

La ausencia de asociación no impide revisar la cotización, pero aparece como dato trazable y no inventado.

## Comparativo MVP

Por cada renglón se conserva:

- producto y producto de catálogo cuando existe;
- proveedor;
- marca/modelo;
- cantidad;
- precio unitario y total;
- moneda;
- entrega;
- cumplimiento técnico;
- notas;
- quote/page/evidence/confidence de origen;
- criterios normalizados y score.

Configuración `mvp-1`:

- cumplimiento técnico: 50 %;
- precio: 35 %;
- entrega: 15 %.

Precio y entrega se comparan dentro del mismo producto. Los datos ausentes reciben un valor neutral de 0.5 y generan una advertencia explícita; no se rellenan con IA.

## Recomendación

La recomendación contiene:

- proveedor recomendado;
- productos considerados;
- criterios y pesos;
- puntuación;
- explicación;
- advertencias;
- `human_review_required: true`;
- `decision: recommendation_only`.

No existe adjudicación o compra automática en esta iteración.

## Endpoints nuevos

```text
POST /api/v1/tenders/{tender_id}/suppliers/{tender_supplier_id}/quotes
GET  /api/v1/tenders/{tender_id}/quotes
GET  /api/v1/quotes/{quote_id}
POST /api/v1/quotes/{quote_id}/review
POST /api/v1/tenders/{tender_id}/comparison
GET  /api/v1/tenders/{tender_id}/comparison
GET  /ready
```

La carga de cotización usa `multipart/form-data`, un único PDF y `uploaded_by_user_id`. Se admite `X-Correlation-ID` para propagar correlación a la tarea de análisis.

## Configuración nueva

```text
SMARTQUOTE_QUOTE_AI_PROMPT_VERSION=1.0.0
SMARTQUOTE_COMPARISON_SCORING_CONFIG_VERSION=mvp-1
```

Se reutilizan `SMARTQUOTE_AI_MODEL`, costos por millón de tokens, storage, límites PDF y credenciales OpenAI ya existentes.

## Health y readiness

- `GET /health`: proceso vivo y metadata de aplicación.
- `GET /ready`: ejecuta `SELECT 1` y devuelve `503` cuando la base de datos no está disponible.

## Seguridad

La cotización reutiliza `DocumentFileValidator`:

- tamaño máximo configurado;
- MIME declarado `application/pdf`;
- contenido no vacío;
- firma PDF dentro del encabezado permitido;
- SHA-256;
- nombre normalizado;
- storage privado por clave opaca.

No se registran credenciales o PDFs completos en auditoría. Los errores HTTP del adaptador IA no incluyen el cuerpo de respuesta del proveedor.

## Verificación

La fuente de verdad de verificación es GitHub Actions `SmartQuote CI`. El PR de Iteración 9 debe permanecer draft hasta que pasen:

- Ruff;
- compileall;
- unit tests;
- integration tests con PostgreSQL/Redis;
- ciclo Alembic upgrade/downgrade/upgrade;
- cobertura >= 90 %;
- contrato OpenAPI;
- Docker build.

Los resultados finales de CI se consignan en el reporte de cierre de la iteración; este documento no debe declarar una verificación que no haya ocurrido.
