# Iteración 12 — Recepción y análisis manual de cotizaciones

## Alcance implementado

La recepción continúa siendo manual. SmartQuote AI no lee inbox, Gmail, Microsoft Graph ni conversaciones de proveedores.

El flujo implementado es:

```text
RFQ sent/delivered/responded
        ↓
manual PDF/XLSX/DOCX upload
        ↓
validation + SHA-256 + private FileStorage
        ↓
Quote + QuoteDocument
        ↓
QuoteTaskRecord + Celery
        ↓
text/table extraction
        ↓
AIExtractionService / structured schema
        ↓
QuoteExtractionRun + QuoteEvidenceReference
        ↓
deterministic normalization/matching/compliance
        ↓
QuoteItems candidates + warnings
        ↓
pending_review
        ↓
human corrections + QuoteItemRevision
        ↓
approved / rejected
```

## Compatibilidad

La implementación extiende el módulo de Iteración 9 y no crea un segundo agregado de cotización.

Se conservan:

- `Quote`;
- `QuoteExtractionRun`;
- `QuoteItem`;
- `AIExtractionService`;
- `FileStorage`;
- cola Celery `quote-analysis`;
- endpoint legacy por `tender_supplier_id`;
- comparación determinista existente.

Los campos de archivo existentes en `Quote` permanecen como snapshot de compatibilidad; `QuoteDocument` es la relación explícita usada por el flujo nuevo.

## Formatos soportados

### PDF

Validación de firma `%PDF-`. Extracción mediante los extractores existentes y fallback `PyMuPDF` / `pdfplumber`.

### XLSX

Sólo `.xlsx` Open XML. El lector procesa XML dentro del ZIP, conserva hoja/fila/celda y utiliza únicamente datos presentes. Las fórmulas no se evalúan. `.xlsm` y `.xls` se rechazan.

### DOCX

Sólo `.docx` Open XML. El lector procesa párrafos y filas de tablas. `.docm` y `.doc` se rechazan.

## Seguridad de archivos

- tamaño máximo configurable;
- extensión permitida;
- MIME declarado compatible;
- firma/contenedor real;
- SHA-256;
- nombre de archivo sin rutas;
- no macros;
- no ejecución de fórmulas;
- no vínculos externos;
- no contenido embebido ejecutable;
- almacenamiento privado mediante `FileStorage`.

## Duplicados

La clave persistida continúa siendo:

```text
tender_id + supplier_id + file_hash
```

El endpoint nuevo devuelve la cotización existente con `duplicate_detected=true` y no escribe nuevamente el archivo. El endpoint legacy conserva su semántica histórica de conflicto 409.

## Estado de Quote

```text
received
  → validating
  → extracting
  → extracted
  → normalized
  → pending_review
  → approved
```

Alternativas: `rejected`, `failed`.

`included_in_comparison` se conserva como estado posterior a `approved` por compatibilidad con la Iteración 9.

No existe transición automática `received → approved`.

## Extracción documental y evidencia

Cada sección extraída recibe un localizador estable:

- PDF: `page:<n>`;
- XLSX: `sheet:<name>:row:<n>`;
- DOCX: `paragraph:<n>` o `table:<n>:row:<n>`.

`QuoteEvidenceReference` enlaza el campo extraído con `QuoteDocument` y `QuoteExtractionRun`. Para evidencia marcada como encontrada, el fragmento debe existir en el texto de la sección indicada.

## Tracking de IA

`QuoteExtractionRun` registra:

- quote/documento;
- run number;
- provider;
- model;
- prompt version;
- schema version/hash;
- extractor name/version;
- extraction fingerprint;
- status;
- provider response ID;
- input/output tokens;
- estimated cost USD;
- duration;
- error;
- timestamps;
- si el run es la fuente aprobada.

El fingerprint reutilizable se deriva de:

```text
file_hash
+ extractor_version
+ model
+ prompt_version
+ schema_version
+ schema_hash
```

Un reprocess explícito crea otro run versionado. No elimina el anterior.

## IA

Puerto utilizado: `AIExtractionService`.

Adaptador configurado: `OpenAIExtractionService` / Responses API.

Modelo por defecto: `gpt-5-mini`.

Prompt de quotes: `quote_extraction/v2`, schema `2.0.0`.

El schema exige distinguir `found`, `not_found`, `inferred` y `ambiguous`. El contrato prohíbe inventar o calcular precios, cantidades, monedas, entrega, marca, modelo o cumplimiento.

## Normalización

La normalización es determinista:

- moneda en código explícito cuando puede normalizarse sin inferencia;
- cantidad positiva;
- unidad mediante aliases controlados;
- entrega en días cuando ya está expresada como tal;
- precios no negativos.

No se realiza conversión de moneda.

Un `total_price` faltante permanece `null`; no se deriva a partir de cantidad y precio unitario.

Si existen los tres valores y la igualdad no concuerda dentro de tolerancia, se agrega `PRICE_CALCULATION_MISMATCH`; el sistema no corrige el precio.

## Matching

`QuoteProductMatcher` devuelve:

- `matched`;
- `possible_match`;
- `unmatched`;
- score 0–1;
- razón legible.

Se consideran nombre, descripción, categoría/especificaciones disponibles, unidad y cantidad. Una coincidencia posible no se convierte en match definitivo sin revisión.

## Cumplimiento técnico

`TechnicalComplianceEvaluator` usa las especificaciones estructuradas del `CatalogProduct` y las especificaciones citadas por la cotización.

Resultados:

- `compliant`;
- `non_compliant`;
- `partial`;
- `unknown`.

Ausencia de evidencia implica `unknown`, nunca `compliant`.

## Confidence

Umbrales configurables:

- alta: >= 0.90;
- media: >= 0.70 y < 0.90;
- baja: < 0.70.

Confidence prioriza revisión; no elimina revisión humana de precio, cantidad, moneda o cumplimiento.

## Revisión humana

Los `QuoteItem` actuales pueden modificarse únicamente cuando la Quote está en `pending_review`.

Cada cambio crea `QuoteItemRevision` con:

- before;
- after;
- campos modificados;
- usuario;
- timestamp.

`original_extracted` y `QuoteEvidenceReference` no se sobrescriben.

La aprobación exige para cada item actual:

- `product_id` resuelto como `matched`;
- cantidad revisada;
- precio unitario o total;
- moneda explícita.

Una Quote aprobada no puede editarse ni reprocessarse silenciosamente.

## Procesamiento asíncrono

`QuoteTaskRecord` registra:

- quote;
- correlation ID;
- task name;
- queued/running/succeeded/failed/retry_pending;
- attempt count;
- force reprocess;
- error;
- timestamps.

La cola sigue siendo `quote-analysis`. Los errores transitorios de almacenamiento/proveedor son reintentables; errores de validación del contenido no se clasifican como retry automático.

## Endpoints

- `POST /api/v1/tenders/{tender_id}/quotes`
- `GET /api/v1/tenders/{tender_id}/quotes`
- `GET /api/v1/quotes/{quote_id}`
- `POST /api/v1/quotes/{quote_id}/documents`
- `GET /api/v1/quotes/{quote_id}/documents`
- `POST /api/v1/quotes/{quote_id}/process`
- `GET /api/v1/quotes/{quote_id}/processing-status`
- `GET /api/v1/quotes/{quote_id}/items`
- `PATCH /api/v1/quotes/{quote_id}/items/{item_id}`
- `GET /api/v1/quotes/{quote_id}/evidence`
- `POST /api/v1/quotes/{quote_id}/submit-review`
- `POST /api/v1/quotes/{quote_id}/approve`
- `POST /api/v1/quotes/{quote_id}/reject`
- `POST /api/v1/quotes/{quote_id}/reprocess`

Los endpoints legacy de Iteración 9 se mantienen.

## Frontend

La vista `Cotizaciones` permite:

- seleccionar proveedor aprobado;
- seleccionar RFQ enviada o usar la más reciente;
- subir PDF/XLSX/DOCX;
- ver estado;
- ver summary y runs;
- ver requested product vs quoted item;
- ver warnings, confidence, match y compliance;
- ver evidencia;
- corregir item;
- aprobar/rechazar;
- reprocessar.

## Comparación

La comparación existente sigue usando sólo Quotes aprobadas. Si para un mismo producto existen monedas distintas, el motor no aplica FX ni compara los importes directamente; agrega un warning y deja el criterio precio neutral para revisión.

## Auditoría

Eventos principales:

- `QuoteReceived`;
- `QuoteFileStored`;
- `QuoteAnalysisStarted`;
- `QuoteAnalyzed`;
- `QuoteNormalized`;
- `QuoteSubmittedForReview`;
- `QuoteItemCorrected`;
- `QuoteApproved`;
- `QuoteRejected`;
- `QuoteReprocessed`.

No se guarda el documento completo en `AuditLog`.

## Verificación

El workflow focalizado es `.github/workflows/iteration-12-quotes.yml`.

La Iteración no debe considerarse terminada hasta que se verifiquen además el CI global, migración completa, frontend, Docker Compose, health/readiness y el flujo manual E2E.
