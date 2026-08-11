# Iteración 13 — Análisis IA de cotizaciones

## Estado inicial auditado

La rama parte de `main` después de la fusión del PR #13. El repositorio ya contenía componentes adelantados del análisis de cotizaciones: `QuoteExtractionRun`, `QuoteItem`, `QuoteEvidenceReference`, `AIExtractionService`, OpenAI Structured Outputs, Celery, matching determinístico y revisión humana.

Esta iteración no duplica esos componentes. Consolida el contrato para separar recepción manual y ejecución de IA, y agrega la pieza persistente faltante: `ExtractionArtifact`.

## Pipeline

```text
QuoteDocument almacenado
  -> ready_for_analysis
  -> POST /analyze
  -> QuoteTaskRecord queued
  -> Celery smartquote.quotes.analyze
  -> extracción documental
  -> AIExtractionService
  -> Structured Output
  -> QuoteExtractionRun + ExtractionArtifact + Evidence + QuoteItems
  -> analyzed
  -> pending_review
```

No existe transición automática a `approved`.

## Endpoints de Iteración 13

| Método | Endpoint | Uso |
|---|---|---|
| POST | `/api/v1/quotes/{id}/analyze` | Encola análisis explícito |
| GET | `/api/v1/quotes/{id}/analysis` | Estado, run, artifact, items y evidencia |
| GET | `/api/v1/quotes/{id}/items` | Items estructurados |
| POST | `/api/v1/quotes/{id}/reanalyze` | Nuevo análisis versionado |

Los endpoints legacy `/process` y `/reprocess` permanecen por compatibilidad; no son el contrato recomendado.

## Esquema IA

Se reutiliza `backend/app/prompts/quote_extraction/v2/prompt.json`, con Structured Output estricto y estados `found`, `not_found`, `inferred` y `ambiguous`. Los campos ausentes permanecen `null`; no se calcula un total faltante ni se convierte moneda.

Configuración principal:

```text
SMARTQUOTE_AI_MODEL=gpt-5-mini
SMARTQUOTE_QUOTE_AI_PROMPT_VERSION=2.0.0
SMARTQUOTE_AI_TEMPERATURE=0
SMARTQUOTE_QUOTE_CONFIDENCE_HIGH_THRESHOLD=0.90
SMARTQUOTE_QUOTE_CONFIDENCE_MEDIUM_THRESHOLD=0.70
SMARTQUOTE_QUOTE_PROCESSING_MAX_RETRIES=3
```

## Runs, artifact, evidencia y costos

`QuoteExtractionRun` registra provider/model, prompt/schema/extractor, `extraction_fingerprint`, tokens, costo estimado, duración, errores y timestamps.

`quote_extraction_artifacts` conserva la salida estructurada original validada de cada run.

`QuoteEvidenceReference` conserva documento, locator, fragmento, método, finding status y confidence. Un item sin evidencia queda marcado `EVIDENCE_MISSING`.

Los costos se calculan con las tarifas configurables `SMARTQUOTE_AI_INPUT_COST_PER_MILLION_TOKENS` y `SMARTQUOTE_AI_OUTPUT_COST_PER_MILLION_TOKENS`; no se hardcodean precios de modelos.

## Idempotencia

Fingerprint:

```text
file_hash + extractor_version + model + prompt_version + schema_version + schema_hash
```

Un run completado con artifact e items se reutiliza sin otra llamada IA. Un reanálisis explícito crea un run nuevo.

## Retries

Celery usa backoff y jitter. Son transitorios HTTP 408/425/429, HTTP 5xx, timeout y errores temporales de red. No se reintentan schema inválido, archivo no procesable, reglas de negocio ni HTTP 4xx permanente.

## Auditoría

Eventos normalizados:

- `quote.analysis_started`
- `quote.analysis_completed`
- `quote.analysis_failed`
- `quote.reanalysis_requested`
- `quote.item_extracted`
- `quote.item_flagged_for_review`

No se escriben documentos completos ni secretos en AuditLog.

## Frontend

La vista de cotizaciones separa `Cargar cotizacion` de `Analizar cotizacion`, muestra estado, items, precio, cantidad, moneda, marca/modelo, entrega, confidence, evidencia y señales `Extraido automaticamente` / `Requiere revision`.

## Fuera de alcance

No se añade ni amplía comparación, scoring, recomendación, selección automática, negociación, inbox automático, Gmail/Graph, OCR avanzado, RAG o agentes. Código histórico de comparación ya presente se conserva sin cambios funcionales.

## Verificación requerida

```bash
cd backend
uv sync --frozen
uv run ruff check .
uv run pytest
uv run alembic upgrade head
uv run alembic downgrade base
uv run alembic upgrade head

cd ../frontend
npm ci
npm run build
```

No existe mypy/pyright configurado actualmente, por lo que no se declara un type-check gate inexistente.
