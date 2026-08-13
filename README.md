# SmartQuote AI

SmartQuote AI es un monolito modular para automatizar, con revisión humana y trazabilidad, el flujo de compras asociado a licitaciones.

## Estado del producto

El **MVP aprobado** termina en un comparativo básico determinista:

```text
Licitación
→ documentos
→ extracción de texto
→ extracción IA del catálogo
→ revisión/aprobación humana
→ proveedores
→ RFQ
→ envío real o simulado
→ recepción manual de cotizaciones
→ análisis IA de cotizaciones
→ revisión/aprobación humana
→ comparativo determinista
```

La Iteración 17 añade como capacidad **post-MVP** un escenario de recomendación determinista, explicable y sujeto a revisión humana:

```text
comparativo v2 ready
→ pesos explícitos del usuario
→ evaluación de elegibilidad
→ scoring reproducible
→ recomendación ready o withheld
→ revisión humana obligatoria
```

La recomendación no adjudica la licitación, no cambia el estado a `awarded`, no aplica conversión FX y no realiza llamadas adicionales a IA.

Todavía no se implementan adjudicación automática, negociación automática, ERP, compras automáticas, OCR completo, multi-tenant, agentes autónomos ni microservicios.

## Arquitectura

El backend mantiene Clean Architecture sobre un monolito modular:

```text
backend/app/
├── domain/
├── application/
│   ├── use_cases/
│   ├── services/
│   ├── ports/
│   └── dtos/
├── infrastructure/
│   ├── db/
│   ├── storage/
│   ├── extraction/
│   ├── ai/
│   ├── email/
│   ├── search/
│   └── tasks/
├── api/
└── config/
```

Principios del proyecto:

- reglas e invariantes en Domain;
- orquestación en Application mediante puertos;
- SQLAlchemy, PostgreSQL, OpenAI, filesystem, email y Celery en Infrastructure;
- rutas FastAPI delgadas;
- persistencia y auditoría de estados relevantes;
- idempotencia para operaciones externas y reprocesamientos;
- resultados automáticos sujetos a revisión humana antes de avanzar a etapas sensibles.

## Stack

- Python 3.12
- FastAPI
- SQLAlchemy
- PostgreSQL 16
- Alembic
- Celery + Redis
- OpenAI mediante puerto desacoplado
- React + TypeScript + Vite
- Docker Compose
- Ruff + pytest

## Servicios locales

```bash
docker compose up --build
```

| Servicio | Función | Puerto host |
|---|---|---|
| `api` | FastAPI | `8000` |
| `worker` | tareas Celery | — |
| `beat` | recuperación/detección periódica | — |
| `postgres` | persistencia | `5433` |
| `redis` | broker/backend Celery | `6379` |
| `mailpit` | SMTP de desarrollo y UI de correo | `1025` / `8025` |

Aplicar migraciones:

```bash
docker compose run --rm api uv run alembic upgrade head
```

Swagger:

```text
http://localhost:8000/docs
```

## Frontend

```bash
cd frontend
npm ci
npm run dev
```

Por defecto Vite redirige `/api` y `/health` al backend local. También puede configurarse una URL explícita:

```bash
VITE_API_BASE_URL=http://127.0.0.1:8000 npm run dev
```

Build de producción:

```bash
npm run build
```

La UI usa inicialmente el usuario operativo:

```text
00000000-0000-0000-0000-000000000001
```

Puede cambiarse desde la barra lateral.

### Vistas disponibles

- Tablero
- Licitaciones
- Documentos
- Catálogo
- Proveedores
- RFQs
- Cotizaciones
- Comparativo

La vista **Comparativo** conserva primero la matriz v2 descriptiva y, debajo, permite generar escenarios post-MVP de recomendación. Los tres pesos empiezan vacíos; la interfaz exige una suma visible de 100% y no impone pesos predeterminados.

## Pipeline asíncrono

Celery se utiliza para operaciones largas o con proveedores externos:

- procesamiento documental;
- extracción IA del catálogo;
- descubrimiento de proveedores;
- entrega de RFQ;
- análisis de cotizaciones.

El worker escucha:

```text
document-processing
ai-extraction
supplier-discovery
rfq-delivery
quote-analysis
```

El comparativo y la recomendación son deterministas/transaccionales y no requieren Celery ni llamadas adicionales a IA.

## Comparativo v2

Endpoints principales:

| Método | Ruta | Función |
|---|---|---|
| `POST` | `/api/v1/tenders/{tender_id}/comparisons` | genera o reutiliza el comparativo vigente |
| `GET` | `/api/v1/tenders/{tender_id}/comparisons` | obtiene el comparativo más reciente |
| `GET` | `/api/v1/comparisons/{comparison_id}` | obtiene un comparativo por id |

La identidad reproducible considera:

```text
tender_id
+ catálogo aprobado/versionado
+ versión de cotizaciones aprobadas
+ comparison_rules_version
```

Reglas importantes:

- sólo se comparan datos aprobados;
- un producto no cotizado aparece explícitamente como faltante, nunca como precio cero;
- no se convierten monedas automáticamente;
- no se asumen equivalencias de unidades no declaradas;
- `unknown` nunca equivale a `compliant`;
- warnings no críticos no invalidan toda la matriz;
- inconsistencias críticas producen un resultado `invalid`;
- el resultado conserva referencias a Quote, QuoteItem y evidencia de origen;
- generar el comparativo no selecciona ni recomienda un proveedor.

## Recomendación explicable

La recomendación de Iteración 17 consume únicamente un `Comparison` v2 persistido en estado `ready`.

Endpoints:

| Método | Ruta | Función |
|---|---|---|
| `POST` | `/api/v1/comparisons/{comparison_id}/recommendations` | genera o reutiliza un escenario con pesos explícitos |
| `GET` | `/api/v1/comparisons/{comparison_id}/recommendations` | obtiene el escenario más reciente |
| `GET` | `/api/v1/recommendations/{recommendation_id}` | obtiene un escenario por id |

Cada request define pesos para:

- cumplimiento técnico;
- precio;
- entrega.

Los pesos deben estar entre 0 y 1 y sumar 1. No existe un 50/35/15 oculto ni otro preset en backend o frontend.

Reglas principales:

- un proveedor debe cubrir todos los productos con ofertas válidas y cantidad/unidad compatible;
- un criterio con peso mayor que cero exige datos comparables en todos los productos;
- un criterio con peso cero no bloquea por ausencia de sus propios datos;
- `non_compliant`, ofertas faltantes/inválidas o cantidades incompatibles excluyen al proveedor;
- precio no comparable no se corrige mediante FX;
- entrega ambigua no se convierte automáticamente a días;
- el score existe únicamente para candidatos elegibles y conserva sus componentes;
- si no hay candidato elegible, el resultado es `withheld`;
- si el primer lugar está empatado, el resultado también es `withheld`: no hay desempate por UUID, nombre u orden;
- un resultado `ready` sigue siendo asesor y persiste `human_review_required=true`;
- generar una recomendación no cambia `Tender.status` ni ejecuta una adjudicación.

La identidad del escenario considera:

```text
comparison_id
+ comparison_key
+ recommendation_policy_version
+ pesos canónicos
```

Cambiar los pesos genera un escenario nuevo y conserva el historial; repetir exactamente el mismo escenario reutiliza su registro.

## Configuración

Copiar o adaptar `.env.example`. Los secretos reales no deben versionarse.

Variables destacadas:

```text
SMARTQUOTE_DATABASE_URL
SMARTQUOTE_STORAGE_ROOT
SMARTQUOTE_CELERY_BROKER_URL
SMARTQUOTE_CELERY_RESULT_BACKEND
SMARTQUOTE_OPENAI_API_KEY
SMARTQUOTE_AI_MODEL
SMARTQUOTE_AI_PROMPT_VERSION
SMARTQUOTE_QUOTE_AI_PROMPT_VERSION
SMARTQUOTE_EMAIL_MODE
SMARTQUOTE_COMPARISON_RULES_VERSION
SMARTQUOTE_RECOMMENDATION_POLICY_VERSION
```

`SMARTQUOTE_EMAIL_MODE=simulation` permite probar RFQ sin enviar correo externo. SMTP puede configurarse cuando exista un servidor real.

`SMARTQUOTE_RECOMMENDATION_POLICY_VERSION` versiona las reglas deterministas del motor; no define pesos para el usuario.

## Pruebas y calidad

Backend:

```bash
cd backend
uv sync --frozen
uv run alembic upgrade head
uv run pytest -q
uv run ruff check .
uv run python -m compileall app tests alembic
```

Cobertura completa:

```bash
uv run --with coverage coverage run --source=app -m pytest -q
uv run --with coverage coverage report -m
```

Frontend:

```bash
cd frontend
npm ci
npm run build
```

GitHub Actions mantiene workflows generales y gates específicos por iteración. El gate global conserva cobertura mínima del 90% y la Iteración 17 añade validación focalizada de migración, reglas de recomendación, OpenAPI e interfaz.

## Trazabilidad

Las extracciones automáticas conservan, cuando aplica:

- documento/origen;
- página o locator;
- ExtractionRun/Artifact;
- provider y modelo;
- prompt/schema/version;
- confidence;
- tokens y costo estimado;
- errores y duración;
- evidencia textual;
- historial de correcciones humanas.

Las cotizaciones aprobadas son la fuente autorizada para el comparativo; una corrección humana no borra la extracción original ni su evidencia.

Los escenarios de recomendación conservan comparativo fuente, versión de política, pesos exactos, candidatos, scores, exclusiones, explicación, warnings y usuario generador.

## Documentación técnica

Los ADRs están en `docs/adr/`. Entre los documentos recientes:

- `docs/iteration-12-validation.md`
- `docs/iteration-13-validation.md`
- `docs/iteration-14-validation.md`
- `docs/iteration-15-mvp-completion.md`
- `docs/iteration-16-document-subsystem-hardening.md`
- `docs/iteration-17-explainable-recommendation.md`
- `docs/adr/0004-quote-document-processing.md`
- `docs/adr/0005-quote-ai-analysis.md`
- `docs/adr/0006-deterministic-quote-comparison.md`
- `docs/adr/0007-explainable-human-gated-recommendation.md`

## Límite actual

El MVP sigue terminando en el comparativo descriptivo. La Iteración 17 es una capa post-MVP de apoyo a la decisión: puede recomendar de forma reproducible o retener la recomendación, pero **no adjudica**.

La siguiente frontera funcional debe separar explícitamente la decisión humana de adjudicación de cualquier automatización posterior. No se debe convertir `Recommendation.ready` en `Tender.awarded` de forma implícita.
