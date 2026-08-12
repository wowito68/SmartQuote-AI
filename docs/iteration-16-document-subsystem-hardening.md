# Iteración 16: Hardening del subsistema documental

## Contexto

Esta iteración parte del repositorio existente después de la Iteración 15. El subsistema documental no se reconstruye: SmartQuote AI ya dispone de carga PDF, validación, SHA-256, almacenamiento privado, `TenderDocument`, extracción de texto por página, `DocumentPage`, `ExtractionRun`, evaluación de calidad, Celery/Redis y endpoints de consulta.

El objetivo de esta iteración es cerrar únicamente las brechas encontradas al contrastar esa implementación con el contrato documental del MVP.

## Alcance implementado

### 1. Contrato `FileStorage`

`FileStorage` incorpora:

```python
exists(storage_key: str) -> bool
```

`LocalFileStorage` implementa la operación usando la misma resolución confinada de claves que `read` y `delete`. Una clave no puede escapar de la raíz privada y los errores de acceso continúan traduciéndose a `DocumentStorageFailure`.

El pipeline valida la existencia del objeto antes de leerlo. Un archivo ausente deja el documento en `failed` y no se transforma en un error genérico del filesystem.

### 2. Duplicados concurrentes

La restricción PostgreSQL existente sigue siendo la autoridad:

```text
UNIQUE(tender_id, file_hash)
```

El `SELECT` previo se mantiene como optimización y para devolver el error antes de escribir cuando el duplicado ya es visible, pero ya no es la única protección.

`SqlAlchemyTenderDocumentRepository` traduce exclusivamente una violación de `uq_tender_documents_tender_file_hash` a `DuplicateDocument`. Otras violaciones de integridad se vuelven a propagar y no se ocultan como duplicados.

Si dos requests pasan simultáneamente el precheck y una pierde la carrera al persistir:

1. PostgreSQL rechaza la segunda fila;
2. Infrastructure traduce el constraint a `DuplicateDocument`;
3. Application hace rollback de la carga;
4. elimina mediante compensación los archivos privados escritos por esa request;
5. registra `DuplicateDocumentDetected` en una transacción limpia;
6. el API conserva el contrato HTTP `409 duplicate_document`.

Esto cierra la deuda de concurrencia documentada desde la Iteración 4.

### 3. Trazabilidad de extracción

`ExtractionRun` incorpora el campo explícito:

```text
extraction_type = "text"
```

El valor se persiste y se expone en `GET /api/v1/documents/{document_id}/extraction`.

No se agrega `extraction_method` duplicado a cada `DocumentPage`: el método y su versión ya están determinados por `extraction_run_id -> ExtractionRun.extractor_name/extractor_version`. Mantenerlos en ambos sitios introduciría denormalización sin aportar evidencia adicional.

No se inventa `confidence` por página. Los extractores actuales (PyMuPDF y pdfplumber) no entregan una métrica de confianza homogénea que pueda persistirse con significado comparable. Las páginas ya conservan metadata verificable: dimensiones, caracteres, palabras, densidad y duración.

### 4. Retry e idempotencia

`ValidateDocumentForProcessing` ahora normaliza los estados `uploaded` y `failed` a `queued` antes de reclamar el documento para procesamiento. Esto permite una redelivery/re-ejecución legítima del pipeline sin saltarse la máquina de estados.

No se agregó `autoretry_for=Exception` a Celery. Un PDF inválido, un hash corrupto o un archivo ausente son errores permanentes y no deben entrar en un loop automático. La re-ejecución es segura y los mecanismos existentes pueden reenviar tareas recuperables.

La idempotencia existente se conserva:

```text
processing_key = SHA256(file_hash + versiones de estrategia + configuración canónica)
```

Además:

- `UNIQUE(document_id, processing_key)` evita runs duplicados compatibles;
- `UNIQUE(extraction_run_id, page_number)` evita páginas duplicadas;
- `replace_pages` reemplaza evidencia parcial del mismo run;
- una extracción completada compatible se reutiliza.

## Persistencia

Se añade la migración:

```text
c8f3a05d6e94_document_subsystem_hardening.py
```

Revisión anterior:

```text
b7e2f94c5d83
```

La migración agrega `extraction_runs.extraction_type VARCHAR(30) NOT NULL`, usando `text` únicamente como default de backfill para filas históricas y retirando el server default después del upgrade. El downgrade elimina la columna.

No se modifica la tabla `document_pages`, porque método y versión permanecen normalizados en `ExtractionRun` y no existe confidence calculable actualmente.

## API

No se crean endpoints nuevos. Se reutilizan los existentes:

```text
POST /api/v1/tenders/{tender_id}/documents
GET  /api/v1/tenders/{tender_id}/documents
GET  /api/v1/documents/{document_id}
GET  /api/v1/documents/{document_id}/status
GET  /api/v1/documents/{document_id}/pages
GET  /api/v1/documents/{document_id}/quality
GET  /api/v1/documents/{document_id}/extraction
```

El único cambio de contrato de respuesta es `extraction_type` en la consulta del run de extracción.

## Frontend

No se realizan cambios. La feature `frontend/src/features/documents/DocumentsPanel.tsx` ya permite seleccionar/subir PDFs, listar documentos, mostrar estados, descargar y reportar errores mediante el flujo existente. `StatusBadge` ya puede representar estados como `needs_ocr`.

## Tests agregados o reforzados

La iteración agrega cobertura explícita para:

- `FileStorage.exists` existente/no existente;
- protección de path traversal también en `exists`;
- traducción del constraint real `(tender_id, file_hash)` a `DuplicateDocument`;
- carrera conceptual después de un precheck exitoso;
- compensación de storage ante esa carrera;
- auditoría `DuplicateDocumentDetected` en la colisión concurrente;
- `extraction_type=text` en el API;
- retry de un documento desde `failed`;
- ausencia de duplicados de `ExtractionRun` y `DocumentPage` después del retry.

## Gate de CI

`.github/workflows/iteration-16-documents.yml` ejecuta sobre PostgreSQL 16 y Redis 7:

```text
uv sync --frozen
uv run ruff check . --output-format=github
uv run ruff format --check .
uv run alembic upgrade head
uv run alembic downgrade b7e2f94c5d83
uv run alembic upgrade head
uv run alembic current
pytest documental enfocado
```

El CI global de SmartQuote continúa ejecutando full pytest, cobertura, OpenAPI, Docker y el ciclo global de migraciones.

## Decisiones arquitectónicas

No se crea un ADR nuevo porque no se introduce un nuevo patrón arquitectónico. Se completan contratos ya aprobados:

- Application depende de `FileStorage`, no del filesystem;
- PostgreSQL es la última línea de defensa de unicidad;
- Infrastructure traduce detalles de constraints a errores de dominio conocidos;
- Application conserva compensación y auditoría;
- `ExtractionRun` es la fuente normalizada de trazabilidad del extractor;
- el procesamiento sigue siendo asíncrono mediante Celery/Redis.

No se crea un `ADR-0002` de almacenamiento: ese número ya existe en el repositorio y la decisión de almacenamiento local desacoplado ya está documentada en la Iteración 4. Crear otro archivo con el mismo número produciría una colisión documental.

## Fuera de alcance respetado

Esta iteración no añade:

- OCR real;
- extracción IA de productos;
- búsqueda web;
- proveedores;
- RFQ;
- inbox;
- cotizaciones;
- comparativo;
- recomendación;
- S3/MinIO;
- antivirus real.

Las capacidades posteriores que ya existen en el repositorio se preservan sin ampliarlas.

## Deuda técnica restante

- carga/descarga streaming antes de elevar límites de tamaño;
- antivirus real detrás de `FileThreatScanner`;
- política de retención y purga física;
- outbox transaccional si se requiere garantía más fuerte entre commit SQL y publicación Redis;
- estrategia de retry clasificada por error si se desea retry automático;
- S3/MinIO como adaptadores alternativos de `FileStorage`;
- OCR para documentos `needs_ocr`, sólo en una iteración explícitamente aprobada.
