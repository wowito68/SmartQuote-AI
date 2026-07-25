# SmartQuote AI

Backend para administrar licitaciones y sus documentos privados con Clean Architecture.

## Alcance actual

La Iteración 4 agrega recepción, validación, almacenamiento, consulta, descarga y eliminación lógica de documentos PDF asociados a licitaciones.

Incluido:

- gestión CRUD y archivado de licitaciones;
- carga de uno o varios PDFs mediante `multipart/form-data`;
- validación de extensión, MIME declarado y firma binaria PDF;
- límite configurable de tamaño y cantidad por solicitud;
- hash SHA-256 y detección de duplicados por licitación;
- almacenamiento privado local mediante `LocalFileStorage`;
- metadatos persistidos en PostgreSQL;
- descarga privada y soft delete;
- auditoría de cargas, eliminaciones y duplicados.

Fuera de alcance:

- extracción de texto;
- OCR;
- PyMuPDF;
- inteligencia artificial;
- antivirus real;
- tareas asíncronas;
- almacenamiento S3 o MinIO.

## Requisitos

- Python 3.12
- uv
- PostgreSQL 16
- Docker y Docker Compose, opcionales para desarrollo local

## Configuración

```bash
cp .env.example .env
```

Variables documentales:

| Variable | Valor predeterminado | Descripción |
|---|---:|---|
| `SMARTQUOTE_STORAGE_ROOT` | `storage/private` | Directorio privado de archivos |
| `SMARTQUOTE_MAX_DOCUMENT_SIZE_BYTES` | `20971520` | Máximo por archivo, 20 MiB |
| `SMARTQUOTE_MAX_DOCUMENTS_PER_UPLOAD` | `10` | Máximo de archivos por solicitud |

El directorio de almacenamiento no debe exponerse mediante un servidor de archivos estáticos.

## Instalación y ejecución

```bash
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

Con Docker Compose:

```bash
docker compose up --build
```

Docker utiliza un volumen privado llamado `document_storage`, montado en `/app/storage/private`.

Servicios:

- API: `http://localhost:8000`
- Swagger/OpenAPI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- Health check: `http://localhost:8000/health`

## Usuario técnico inicial

Mientras no exista autenticación, la migración registra este usuario para probar los flujos:

```text
ID: 00000000-0000-0000-0000-000000000001
Email: system@smartquote.local
```

Los campos `created_by_user_id`, `uploaded_by_user_id` y `deleted_by_user_id` deben apuntar a usuarios existentes.

## Endpoints

### Licitaciones

| Método | Ruta | Resultado |
|---|---|---|
| `POST` | `/api/v1/tenders` | Crear una licitación |
| `GET` | `/api/v1/tenders` | Listar licitaciones activas |
| `GET` | `/api/v1/tenders/{id}` | Consultar una licitación |
| `PUT` | `/api/v1/tenders/{id}` | Reemplazar datos editables |
| `DELETE` | `/api/v1/tenders/{id}` | Archivar lógicamente |

### Documentos

| Método | Ruta | Resultado |
|---|---|---|
| `POST` | `/api/v1/tenders/{id}/documents` | Cargar uno o varios PDFs |
| `GET` | `/api/v1/tenders/{id}/documents` | Listar documentos activos |
| `GET` | `/api/v1/documents/{id}` | Consultar metadatos |
| `GET` | `/api/v1/documents/{id}/download` | Descargar el PDF privado |
| `DELETE` | `/api/v1/documents/{id}` | Eliminar lógicamente |

## Ejemplo completo

### 1. Crear una licitación

```bash
curl -X POST http://localhost:8000/api/v1/tenders \
  -H 'Content-Type: application/json' \
  -d '{
    "title": "Adquisición de transformadores 2026",
    "description": "Suministro nacional para instalaciones eléctricas.",
    "deadline": "2026-08-31T18:00:00-06:00",
    "created_by_user_id": "00000000-0000-0000-0000-000000000001"
  }'
```

### 2. Cargar uno o varios documentos

```bash
curl -X POST \
  http://localhost:8000/api/v1/tenders/8e2211ec-5f39-4a4d-9844-b8c64e9038c3/documents \
  -F 'uploaded_by_user_id=00000000-0000-0000-0000-000000000001' \
  -F 'files=@bases.pdf;type=application/pdf' \
  -F 'files=@anexo-tecnico.pdf;type=application/pdf'
```

Respuesta `201 Created`:

```json
{
  "items": [
    {
      "id": "f2c7a182-97ba-4828-8621-62282051393d",
      "tender_id": "8e2211ec-5f39-4a4d-9844-b8c64e9038c3",
      "original_file_name": "bases.pdf",
      "mime_type": "application/pdf",
      "file_size": 245760,
      "file_hash": "c4d88d14a6a20d76d70fb5f81cbcc9e1c24407f82d875559b8423a34e3bbfa8a",
      "status": "uploaded",
      "uploaded_by_user_id": "00000000-0000-0000-0000-000000000001",
      "uploaded_at": "2026-07-25T18:00:00Z",
      "updated_at": "2026-07-25T18:00:00Z"
    }
  ],
  "total": 1
}
```

### 3. Listar documentos

```bash
curl http://localhost:8000/api/v1/tenders/8e2211ec-5f39-4a4d-9844-b8c64e9038c3/documents
```

### 4. Consultar metadatos

```bash
curl http://localhost:8000/api/v1/documents/f2c7a182-97ba-4828-8621-62282051393d
```

La API nunca expone la ruta física ni la clave interna de almacenamiento.

### 5. Descargar

```bash
curl -OJ \
  http://localhost:8000/api/v1/documents/f2c7a182-97ba-4828-8621-62282051393d/download
```

La respuesta incluye `Content-Disposition: attachment` y `X-Content-Type-Options: nosniff`.

### 6. Eliminar lógicamente

```bash
curl -X DELETE \
  'http://localhost:8000/api/v1/documents/f2c7a182-97ba-4828-8621-62282051393d?deleted_by_user_id=00000000-0000-0000-0000-000000000001'
```

Respuesta `204 No Content`. El documento deja de listarse y descargarse. El archivo privado se conserva hasta que exista una política de retención y purga física.

## Uso desde Swagger

1. Abrir `http://localhost:8000/docs`.
2. Crear o copiar el UUID de una licitación en estado `draft` o `documents_pending`.
3. Abrir `POST /api/v1/tenders/{tender_id}/documents`.
4. Seleccionar **Try it out**.
5. Capturar `uploaded_by_user_id`.
6. Seleccionar uno o varios archivos en `files`.
7. Ejecutar la solicitud.

El contrato OpenAPI declara explícitamente `multipart/form-data` y un arreglo de archivos binarios.

## Reglas documentales

- Solo se permiten archivos con extensión `.pdf`.
- El MIME declarado debe ser `application/pdf`.
- El contenido debe incluir la firma binaria `%PDF-` en sus primeros 1,024 bytes.
- El archivo no puede estar vacío.
- El tamaño máximo y la cantidad por solicitud son configurables.
- El nombre original no puede contener rutas, separadores ni caracteres de control.
- El SHA-256 se calcula sobre los bytes recibidos.
- Un hash no puede repetirse dentro de la misma licitación, incluso si la carga anterior fue eliminada lógicamente.
- Solo se aceptan cargas cuando la licitación está en `draft` o `documents_pending`.
- Las licitaciones archivadas, cerradas, canceladas o en fases posteriores no aceptan documentos.
- La primera carga cambia una licitación `draft` a `documents_pending`.
- El estado inicial del documento es `uploaded`.

Estados implementados:

```text
uploaded
rejected
deleted
```

No existen estados de extracción, OCR o procesamiento en el dominio de esta iteración.

## Almacenamiento privado

La estructura física es:

```text
storage/private/
└── tenders/
    └── <tender_uuid>/
        └── <document_uuid>.pdf
```

El nombre proporcionado por el usuario se conserva únicamente como metadato. El nombre físico usa UUIDs y no permite controlar rutas del sistema.

`LocalFileStorage`:

- resuelve y verifica que cada ruta permanezca dentro de la raíz privada;
- crea directorios con permisos privados;
- escribe primero en un archivo temporal;
- fuerza la escritura con `fsync`;
- mueve el archivo de forma atómica;
- asigna permisos `0600` al archivo cuando el sistema lo permite.

## Sustituir LocalFileStorage por MinIO o S3

La capa Application depende únicamente de:

```python
class FileStorage(ABC):
    def store(self, tender_id, document_id, content) -> str: ...
    def read(self, storage_key) -> bytes: ...
    def delete(self, storage_key) -> None: ...
```

Para cambiar el backend de almacenamiento:

1. Crear un adaptador que implemente `FileStorage`.
2. Mantener `storage_key` como identificador opaco y no como URL pública.
3. Sustituir la dependencia `get_file_storage` en `app/api/dependencies.py`.
4. No modificar Domain, DTOs, casos de uso ni endpoints.

También existe el puerto `FileThreatScanner` como punto de extensión previo al almacenamiento. No se conecta ningún antivirus en esta iteración.

## Auditoría

Eventos persistidos:

- `DocumentUploaded`: documento, licitación, usuario y hash.
- `DocumentDeleted`: documento, licitación, usuario y hash.
- `DuplicateDocumentDetected`: licitación, usuario, hash y nombre original.

Los eventos se confirman dentro de la misma transacción que sus metadatos, excepto la detección de duplicado, que se registra antes de devolver el conflicto `409`.

## Errores documentales

| HTTP | `code` | Significado |
|---:|---|---|
| `404` | `document_not_found` | Documento inexistente, eliminado o perteneciente a una licitación archivada |
| `409` | `duplicate_document` | Hash repetido en la misma licitación |
| `409` | `document_already_deleted` | Segundo intento de eliminación |
| `409` | `invalid_tender_state` | La licitación no acepta cargas |
| `409` | `tender_already_archived` | La licitación está archivada |
| `413` | `document_too_large` | Archivo o cuerpo multipart superior al límite |
| `422` | `invalid_document_file` | Extensión, MIME, firma, nombre o formulario inválido |
| `422` | `too_many_documents` | Demasiados archivos en una solicitud |
| `422` | `document_user_not_found` | Usuario de carga o eliminación inexistente |
| `503` | `document_storage_unavailable` | Error de lectura o escritura del almacenamiento privado |

## Pruebas y calidad

```bash
cd backend
uv run pytest
uv run --with coverage coverage run --source=app -m pytest -q
uv run --with coverage coverage report --fail-under=90
uv run ruff check .
uv run ruff format --check .
uv run python -m compileall app tests alembic
```

La integración continua valida automáticamente:

- Ruff lint y formato;
- pruebas unitarias;
- pruebas de integración con PostgreSQL 16;
- upgrade, rollback y nuevo upgrade de Alembic;
- cobertura mínima del 90%;
- contrato OpenAPI, incluido multipart;
- construcción de la imagen Docker.

## Documentación técnica

- `docs/iteration-3-tender-management.md`
- `docs/iteration-4-document-management.md`
- `docs/continuous-integration.md`
- `docs/vision-tecnica.md`
- `docs/adr/`
