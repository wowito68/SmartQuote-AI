# SmartQuote AI

Sistema Inteligente para la Automatización del Proceso de Cotizaciones mediante
Inteligencia Artificial.

SmartQuote AI automatiza el flujo de compras para licitaciones: recepción de
documentos, extracción de productos, búsqueda y aprobación de proveedores,
solicitudes de cotización, análisis de respuestas y generación de comparativos.

El proyecto se desarrolla de forma incremental con Clean Architecture. La
Iteración 2 contiene el scaffold funcional del backend, configuración de base de
datos, dominio inicial y persistencia para `User`, `Tender` y `TenderDocument`.

## Requisitos

- Python 3.12
- uv
- Docker
- Docker Compose

## Estructura del proyecto

```text
SmartQuote-AI/
  backend/
    app/
      api/
        routes/
          health.py
      application/
        ports/
          tender_repository.py
      config/
        settings.py
      domain/
        shared/
        tenders/
        users/
      infrastructure/
        db/
          base.py
          session.py
          mappers/
          models/
          repositories/
      main.py
    alembic/
      versions/
      env.py
      script.py.mako
    tests/
      integration/
      unit/
      test_health.py
    Dockerfile
    pyproject.toml
    alembic.ini
  docs/
    adr/
    vision-tecnica.md
  .env.example
  .gitignore
  docker-compose.yml
  README.md
```

## Instalación local

Desde la raíz del repositorio:

```bash
cp .env.example .env
cd backend
uv sync
```

## Ejecución local

```bash
cd backend
uv run uvicorn app.main:app --reload
```

El backend quedará disponible en:

```text
http://localhost:8000
```

Health check:

```bash
curl http://localhost:8000/health
```

Respuesta esperada:

```json
{
  "status": "ok",
  "project_name": "SmartQuote AI",
  "version": "0.1.0",
  "environment": "local"
}
```

## Ejecución con Docker Compose

```bash
docker compose up --build
```

Servicios incluidos en esta iteración:

- `api`: backend FastAPI.
- `postgres`: PostgreSQL 16 para desarrollo local.

El health check sigue disponible en:

```text
http://localhost:8000/health
```

PostgreSQL se publica en el host en el puerto `5433` para evitar conflictos con
instalaciones locales que ya usen `5432`. Dentro de Docker, la API se conecta a
`postgres:5432`.

Para levantar únicamente PostgreSQL:

```bash
docker compose up -d postgres
```

## Configuración

Las variables disponibles están documentadas en `.env.example`.

Prefijo usado por la aplicación:

```text
SMARTQUOTE_
```

Variables actuales:

- `SMARTQUOTE_PROJECT_NAME`
- `SMARTQUOTE_VERSION`
- `SMARTQUOTE_ENVIRONMENT`
- `SMARTQUOTE_API_V1_PREFIX`
- `SMARTQUOTE_DATABASE_URL`

Para desarrollo local puede crearse un archivo `.env` a partir de `.env.example`.
Los archivos `.env` reales no deben versionarse.

Ejemplo local:

```text
SMARTQUOTE_DATABASE_URL="postgresql+psycopg://smartquote:smartquote@localhost:5433/smartquote"
```

## Migraciones

Desde `backend/`, con PostgreSQL levantado:

```bash
uv run alembic upgrade head
```

Crear una nueva migración autogenerada:

```bash
uv run alembic revision --autogenerate -m "describe change"
```

Revertir la última migración:

```bash
uv run alembic downgrade -1
```

Revertir todo el esquema:

```bash
uv run alembic downgrade base
```

## Comandos principales

Desde `backend/`:

```bash
uv sync
uv run uvicorn app.main:app --reload
uv run pytest
uv run ruff check .
uv run python -m compileall app tests
```

Las pruebas de integración usan PostgreSQL real. Antes de ejecutarlas:

```bash
docker compose up -d postgres
cd backend
uv run pytest
```

## Dominio y persistencia

Convenciones actuales:

- `domain/` contiene entidades puras, Value Objects, enums y reglas de negocio.
- `domain/` no importa FastAPI, SQLAlchemy, Alembic ni infraestructura.
- `application/ports/` define interfaces que la infraestructura implementa.
- `infrastructure/db/models/` contiene modelos SQLAlchemy.
- `infrastructure/db/mappers/` traduce entre ORM y dominio.
- `infrastructure/db/repositories/` contiene adaptadores concretos.
- Los repositorios hacen `flush`, pero no `commit`; la transacción queda fuera
  del repositorio para poder introducir Unit of Work en una iteración posterior.
- Las eliminaciones de `Tender` son soft delete mediante `deleted_at`.
- Los estados se guardan como `String` con `CheckConstraint` para evitar acoplar
  el dominio a enums nativos de PostgreSQL en esta etapa.

Tablas iniciales:

- `users`
- `tenders`
- `tender_documents`

## Alcance actual

Incluido:

- estructura mínima del backend;
- configuración con Pydantic Settings;
- FastAPI inicial;
- endpoint `GET /health`;
- SQLAlchemy 2.x configurado;
- Alembic funcional con primera migración;
- dominio inicial: `User`, `Tender`, `TenderDocument`;
- Value Objects iniciales: `EmailAddress`, `FileHash`, `TenderStatus`,
  `DocumentStatus`;
- modelos SQLAlchemy para `users`, `tenders` y `tender_documents`;
- mappers ORM/dominio;
- puerto `TenderRepository`;
- adaptador `SqlAlchemyTenderRepository`;
- configuración de Ruff y Pytest;
- Dockerfile y Docker Compose;
- pruebas de dominio, migración, conexión y repositorio.

No incluido todavía:

- casos de uso;
- endpoints de negocio;
- OpenAI;
- Celery;
- Redis;
- frontend.

## Documentación de arquitectura

La documentación viva del proyecto está en:

- `docs/vision-tecnica.md`
- `docs/adr/`
