# ADR-0005 — Contrato de análisis IA de cotizaciones

- Estado: Aceptado
- Fecha: 2026-08-10
- Iteración: 13

## Contexto

Al iniciar la Iteración 13, `main` ya contenía trabajo adelantado de análisis de cotizaciones proveniente de la Iteración 12: `QuoteExtractionRun`, `QuoteItem`, evidencia, `AIExtractionService`, OpenAI Structured Outputs, Celery y una UI de revisión. El flujo de recepción, sin embargo, iniciaba el análisis automáticamente y el resultado estructurado de IA sólo se conservaba como `raw_response` dentro del run.

La definición autoritativa de Iteración 13 exige separar recepción y análisis, conservar un `ExtractionArtifact`, ejecutar IA únicamente detrás del puerto existente, usar idempotencia y retries controlados y terminar en revisión humana. Comparación, scoring y recomendación quedan fuera de este cambio.

## Decisión

### Recepción y análisis son acciones distintas

La carga manual termina en `ready_for_analysis`. Sólo `POST /api/v1/quotes/{id}/analyze` crea una intención explícita de análisis y publica la tarea Celery.

Lifecycle nuevo:

```text
received -> validating -> ready_for_analysis -> analyzing -> analyzed -> pending_review
```

`approved` y `rejected` siguen siendo decisiones humanas posteriores. Los estados legacy se mantienen únicamente por compatibilidad de datos históricos.

### `QuoteExtractionRun` es el ExtractionRun especializado

No se crea un segundo tracker genérico. `QuoteExtractionRun` ya conserva quote/documento, provider, model, prompt/schema/extractor, fingerprint de entrada, estado, tokens, costo, errores y timestamps. `extraction_fingerprint` funciona como `input_hash`.

### `ExtractionArtifact`

Se crea `quote_extraction_artifacts`, uno-a-uno con el run, con `schema_version`, `structured_output` JSON y `created_at`. `raw_response` del run se mantiene temporalmente por compatibilidad; la migración crea artifacts para runs históricos completados que ya tenían salida estructurada.

### Puerto IA

Application continúa dependiendo sólo de `AIExtractionService`; OpenAI permanece en Infrastructure y usa Structured Outputs.

### Retries

Sólo se consideran transitorios HTTP 408/425/429, HTTP 5xx, timeout y fallos temporales de red/conexión. HTTP 4xx permanente, schema inválido, documento no procesable y validación de negocio no se reintentan automáticamente.

### Revisión humana obligatoria

Tras una extracción exitosa se persisten run, artifact, QuoteItems y evidencia. La Quote pasa por `analyzed` y termina en `pending_review`. Confidence, matching o la respuesta IA nunca llevan automáticamente a `approved`.

### Formatos

PDF es el formato objetivo de aceptación de Iteración 13 y reutiliza PyMuPDF/pdfplumber. El lector OOXML seguro de XLSX/DOCX ya existía en `main`; se conserva para evitar regresiones, pero no se amplía.

## Idempotencia

Fingerprint determinístico:

```text
quote_document_hash + extractor_version + model + prompt_version + schema_version + schema_hash
```

Un run completado con artifact e items puede reutilizarse. `reanalyze` crea deliberadamente un run nuevo versionado.

## Evidencia y confidence

`QuoteEvidenceReference` sigue siendo la evidencia por campo/item. Los fragmentos se verifican contra la sección extraída. Un item sin evidencia se marca `EVIDENCE_MISSING`. Confidence es una señal de revisión, no una garantía de exactitud.

## Consecuencias

- La recepción manual ya no genera costo IA implícito.
- La salida original validada queda auditable en artifact.
- Se preserva compatibilidad de datos históricos.
- El comparador/recomendador preexistente no se modifica ni se amplía en esta iteración.
