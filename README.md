# SmartQuote AI

Backend para administrar licitaciones, almacenar documentos privados y extraer texto de PDFs mediante un pipeline asíncrono auditable.

## Alcance actual

La Iteración 5 agrega:

- Celery como motor de tareas;
- Redis como broker y backend de resultados;
- detección periódica de documentos pendientes;
- extracción de texto por página;
- PyMuPDF como extractor primario;
- pdfplumber como fallback automático;
- evaluación de calidad documental;
- estados `queued`, `processing`, `text_extracted`, `ready_for_ai`, `needs_ocr` y `failed`;
- persistencia de páginas, ejecuciones, configuración, errores y métricas;
- endpoints de consulta para estado, páginas, calidad y extracción;
- logs estructurados en JSON.

Fuera de alcance: OpenAI, OCR, extracción de productos, proveedores, RFQs y procesamiento síncrono.

## Servicios

```bash
docker compose up --build
```

El entorno inicia:

| Servicio | Función |
|---|---|
| `api` | FastAPI y carga de documentos |
| `worker` | ejecución de etapas Celery |
| `beat` | detección periódica de documentos pendientes |
| `redis` | broker y backend Celery |
| `postgres` | metadatos, páginas, métricas y auditoría |

Aplicar migraciones:

```bash
docker compose run --rm api uv run alembic upgrade head
```

Swagger: `http://localhost:8000/docs`

## Pipeline documental

```mermaid
flowchart LR
    A[DocumentUploaded] --> B[DocumentValidation]
    B --> C[TextExtraction]
    C --> D[QualityEvaluation]
    D -->|calidad suficiente| E[ReadyForAI]
    D -->|texto insuficiente| F[NeedsOCR]
    B -->|error| G[Failed]
    C -->|error| G
    D -->|error| G
```

Las etapas se implementan como tareas Celery independientes:

- `smartquote.documents.validate`
- `smartquote.documents.extract_text`
- `smartquote.documents.evaluate_quality`
- `smartquote.documents.finalize`

La carga publica `smartquote.documents.start_pipeline`. El worker orquesta las etapas sin ejecutarlas en el proceso HTTP. Cada etapa también está registrada como tarea Celery independiente. Celery Beat ejecuta `smartquote.documents.detect_pending` para recuperar documentos `uploaded` o `queued` que no hayan sido consumidos.

## Flujo completo

1. `POST /api/v1/tenders/{id}/documents` valida y almacena el PDF privado.
2. Se registra `DocumentUploaded`.
3. El documento cambia de `uploaded` a `queued` y se registra `DocumentQueued`.
4. Después del commit SQL se publica la tarea en Redis.
5. El worker valida nuevamente firma y SHA-256 del archivo almacenado.
6. El documento pasa a `processing`.
7. PyMuPDF extrae texto página por página mediante `Page.get_text("text", sort=True)`.
8. Si falla o la extracción es insuficiente, se ejecuta pdfplumber.
9. Se persisten `ExtractionRun` y cada `DocumentPage`.
10. El documento pasa a `text_extracted`.
11. `DocumentQualityEvaluator` calcula métricas.
12. El documento termina en `ready_for_ai` o `needs_ocr`.
13. Los errores dejan evidencia en `ExtractionRun` y cambian el documento a `failed`.

## Persistencia

### `extraction_runs`

Conserva:

- extractor final y versión;
- configuración canónica;
- clave de idempotencia;
- inicio, final y duración;
- páginas y caracteres extraídos;
- resultado y errores;
- referencia a ejecución reutilizada cuando aplique.

### `document_pages`

Cada página conserva:

- número;
- texto;
- dimensiones;
- caracteres y palabras;
- indicador de página vacía;
- densidad aproximada;
- duración de extracción.

### `document_qualities`

Conserva:

- páginas procesadas y vacías;
- porcentaje de páginas sin texto;
- caracteres extraídos;
- densidad agregada;
- calidad estimada;
- decisión;
- indicador de revisión manual.

## Extractores

`DocumentTextExtractor` desacopla Application de las bibliotecas PDF.

```text
DocumentTextExtractor
├── PyMuPDFExtractor       # primario
└── PdfPlumberExtractor    # fallback
```

La estrategia intenta pdfplumber cuando PyMuPDF:

- produce una excepción;
- no alcanza el mínimo de caracteres;
- supera el porcentaje permitido de páginas vacías;
- no alcanza el promedio mínimo de caracteres por página.

Si ambos resultados existen, se conserva el de mayor cantidad de texto, menor porcentaje vacío y mayor cantidad de páginas.

## Evaluación de calidad

La densidad se calcula como caracteres extraídos entre el área total de las páginas en pulgadas cuadradas.

Decisiones:

- `ready_for_ai`: texto suficiente, pocas páginas vacías y densidad mínima;
- `needs_ocr`: documento vacío o con texto extremadamente escaso;
- `manual_review`: calidad intermedia; se conserva en `DocumentQuality` y el estado operativo se marca `needs_ocr` porque OCR/revisión serán resueltos en una iteración posterior.

Todos los umbrales son configurables mediante variables `SMARTQUOTE_QUALITY_*`.

## Idempotencia

La clave SHA-256 de procesamiento incluye:

- hash SHA-256 del PDF;
- nombre y versión de PyMuPDF;
- nombre y versión de pdfplumber;
- política de fallback;
- configuración de calidad/extracción aplicable.

Una ejecución completada con la misma clave se reutiliza. La restricción única `(document_id, processing_key)` evita ejecuciones válidas duplicadas.

## Endpoints de documentos

| Método | Ruta | Resultado |
|---|---|---|
| `POST` | `/api/v1/tenders/{id}/documents` | Carga PDFs y dispara el pipeline |
| `GET` | `/api/v1/documents/{id}/status` | Estado y fechas del procesamiento |
| `GET` | `/api/v1/documents/{id}/pages` | Texto y métricas por página |
| `GET` | `/api/v1/documents/{id}/quality` | Evaluación de calidad |
| `GET` | `/api/v1/documents/{id}/extraction` | Evidencia de la ejecución |
| `GET` | `/api/v1/documents/{id}/download` | Descarga privada |
| `DELETE` | `/api/v1/documents/{id}` | Eliminación lógica |

No existe endpoint HTTP para iniciar manualmente el pipeline.

## Ejemplo

```bash
curl -X POST http://localhost:8000/api/v1/tenders/TENDER_ID/documents \
  -F 'uploaded_by_user_id=00000000-0000-0000-0000-000000000001' \
  -F 'files=@bases.pdf;type=application/pdf'

curl http://localhost:8000/api/v1/documents/DOCUMENT_ID/status
curl http://localhost:8000/api/v1/documents/DOCUMENT_ID/pages
curl http://localhost:8000/api/v1/documents/DOCUMENT_ID/quality
curl http://localhost:8000/api/v1/documents/DOCUMENT_ID/extraction
```

## Configuración relevante

```text
SMARTQUOTE_CELERY_BROKER_URL=redis://redis:6379/0
SMARTQUOTE_CELERY_RESULT_BACKEND=redis://redis:6379/1
SMARTQUOTE_PENDING_DOCUMENT_SCAN_SECONDS=60
SMARTQUOTE_EXTRACTION_MINIMUM_CHARACTERS=100
SMARTQUOTE_EXTRACTION_MAXIMUM_EMPTY_PAGE_PERCENTAGE=60
SMARTQUOTE_QUALITY_READY_MINIMUM_CHARACTERS=200
SMARTQUOTE_QUALITY_READY_MAXIMUM_EMPTY_PAGE_PERCENTAGE=25
SMARTQUOTE_QUALITY_READY_MINIMUM_DENSITY=1.5
SMARTQUOTE_QUALITY_OCR_MAXIMUM_CHARACTERS=50
SMARTQUOTE_QUALITY_OCR_MINIMUM_EMPTY_PAGE_PERCENTAGE=50
SMARTQUOTE_QUALITY_OCR_MAXIMUM_DENSITY=0.5
```

## Pruebas

```bash
cd backend
uv sync
uv run alembic upgrade head
uv run pytest
uv run ruff check .
uv run python -m compileall app tests alembic
```

La suite incluye PDFs reales pequeños en `tests/fixtures/` y pruebas de:

- extractores;
- fallback;
- métricas;
- estados;
- pipeline completo;
- persistencia de páginas;
- idempotencia;
- endpoints;
- worker Celery con Redis real.

## Documentación técnica

- `docs/iteration-4-document-management.md`
- `docs/iteration-5-text-extraction-pipeline.md`
- `docs/continuous-integration.md`

## Iteración 6: extracción inteligente de catálogo

La Iteración 6 consume únicamente documentos `ready_for_ai` y crea un catálogo sugerido por IA. La respuesta no modifica directamente el dominio: primero se valida con JSON Schema estricto y Pydantic, después se normaliza con reglas determinísticas y finalmente queda en `pending_review`.

### Servicios y configuración

El worker Celery escucha dos colas:

```text
document-processing
ai-extraction
```

Variables principales:

```text
SMARTQUOTE_OPENAI_API_KEY
SMARTQUOTE_OPENAI_BASE_URL=https://api.openai.com/v1
SMARTQUOTE_OPENAI_TIMEOUT_SECONDS=90
SMARTQUOTE_AI_MODEL=gpt-5-mini
SMARTQUOTE_AI_PROMPT_VERSION=1.0.0
SMARTQUOTE_AI_TEMPERATURE=0
SMARTQUOTE_AI_INPUT_COST_PER_MILLION_TOKENS=0
SMARTQUOTE_AI_OUTPUT_COST_PER_MILLION_TOKENS=0
```

Los precios deben configurarse con la tarifa vigente del modelo contratado.

### Endpoints

| Método | Ruta | Función |
|---|---|---|
| `POST` | `/api/v1/tenders/{id}/catalog/extract` | Crea o reutiliza runs y encola extracción |
| `GET` | `/api/v1/tenders/{id}/catalog` | Catálogo, estados y métricas |
| `GET` | `/api/v1/catalog/{product_id}` | Producto, payload original y evidencia |
| `PUT` | `/api/v1/catalog/{product_id}` | Editar, aprobar o rechazar |
| `POST` | `/api/v1/tenders/{id}/catalog/approve` | Snapshot inmutable aprobado |

Ejemplo:

```bash
curl -X POST http://localhost:8000/api/v1/tenders/TENDER_ID/catalog/extract

curl http://localhost:8000/api/v1/tenders/TENDER_ID/catalog

curl -X PUT http://localhost:8000/api/v1/catalog/PRODUCT_ID \
  -H 'Content-Type: application/json' \
  -d '{
    "action": "edit",
    "reviewer_user_id": "00000000-0000-0000-0000-000000000001",
    "quantity": 2500,
    "unit": "m"
  }'

curl -X PUT http://localhost:8000/api/v1/catalog/PRODUCT_ID \
  -H 'Content-Type: application/json' \
  -d '{
    "action": "approve",
    "reviewer_user_id": "00000000-0000-0000-0000-000000000001"
  }'

curl -X POST http://localhost:8000/api/v1/tenders/TENDER_ID/catalog/approve \
  -H 'Content-Type: application/json' \
  -d '{"approved_by_user_id":"00000000-0000-0000-0000-000000000001"}'
```

### Prompts y trazabilidad

El prompt activo está versionado en `backend/app/prompts/catalog_extraction/v1/prompt.json`. La clave idempotente incluye hash del PDF, versión del prompt, modelo y hash del schema. Cada producto conserva el JSON original, página, fragmento, confianza, modelo y prompt; las ediciones humanas se guardan como revisiones separadas.

La explicación técnica completa está en `docs/ai-extraction.md`.

Fuera de alcance: proveedores, RFQs, recepción de correo y análisis de cotizaciones.

## Iteración 7: descubrimiento y gestión de proveedores

La Iteración 7 parte únicamente del último snapshot de catálogo aprobado. El descubrimiento se ejecuta en Celery y deja candidatos para revisión humana; nunca aprueba ni elimina proveedores automáticamente.

### Flujo

```mermaid
flowchart LR
    A[Approved Catalog] --> B[Supplier Discovery]
    B --> C[Deduplication]
    C --> D[Contact Discovery]
    D --> E[Deterministic Matching]
    E --> F[Pending Review]
    F --> G[Approved]
    F --> H[Rejected]
    F --> I[Merged]
```

El modelo distingue:

- `Supplier`: maestro global reutilizable;
- `TenderSupplier`: estado y contexto dentro de una licitación;
- `SupplierContact`: correo, teléfono, WhatsApp o formulario con confianza y fuente;
- `SupplierSource`: evidencia del hallazgo;
- `ProductSupplierMatch`: score explicable por producto.

### Configuración

```text
SMARTQUOTE_SUPPLIER_DIRECTORY_PATH=app/supplier_sources/default_directory.json
SMARTQUOTE_SUPPLIER_SEARCH_COUNTRY=MX
SMARTQUOTE_SUPPLIER_SEARCH_MAX_RESULTS_PER_PRODUCT=10
SMARTQUOTE_SUPPLIER_MATCHING_ALGORITHM_VERSION=1.0.0
```

El worker debe escuchar también la cola `supplier-discovery`:

```bash
uv run celery -A app.infrastructure.tasks.celery_app:celery_app worker \
  --loglevel=INFO \
  --queues=document-processing,ai-extraction,supplier-discovery
```

### Endpoints

| Método | Ruta |
|---|---|
| `POST` | `/api/v1/tenders/{id}/suppliers/discover` |
| `GET` | `/api/v1/tenders/{id}/suppliers` |
| `GET` | `/api/v1/suppliers/{id}` |
| `PUT` | `/api/v1/suppliers/{id}` |
| `POST` | `/api/v1/suppliers/{id}/approve` |
| `POST` | `/api/v1/suppliers/{id}/reject` |
| `POST` | `/api/v1/suppliers/merge` |
| `POST` | `/api/v1/suppliers/manual` |

Ejemplo:

```bash
curl -X POST http://localhost:8000/api/v1/tenders/TENDER_ID/suppliers/discover \
  -H 'Content-Type: application/json' \
  -d '{"requested_by_user_id":"00000000-0000-0000-0000-000000000001"}'

curl http://localhost:8000/api/v1/tenders/TENDER_ID/suppliers

curl -X POST http://localhost:8000/api/v1/suppliers/TENDER_SUPPLIER_ID/approve \
  -H 'Content-Type: application/json' \
  -d '{"reviewer_user_id":"00000000-0000-0000-0000-000000000001"}'
```

El matching es determinístico y pondera nombre (35), categoría (25), palabras clave (20) y especificaciones (20). La deduplicación prioriza dominio, correo y teléfono, y usa nombres como señales adicionales. Las coincidencias inciertas generan sugerencias de fusión para revisión.

La documentación completa está en `docs/supplier-discovery.md`.

Fuera de alcance: RFQs, envío de correos, monitoreo de respuestas y análisis de cotizaciones.
