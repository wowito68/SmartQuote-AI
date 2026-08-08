# ADR 0002 — Cotizaciones, comparativo y recomendación MVP

- Estado: aceptada
- Fecha: 2026-08-08
- Iteración: 9

## Contexto

SmartQuote AI ya implementaba el flujo de licitación, documentos, extracción de texto, extracción IA de catálogo, revisión humana, descubrimiento/aprobación de proveedores y generación/envío de RFQ. El MVP todavía no podía registrar la respuesta documental de un proveedor ni producir un comparativo verificable.

La arquitectura vigente es un monolito modular con dominio independiente de frameworks, casos de uso explícitos, puertos en `application`, adaptadores en `infrastructure`, SQLAlchemy/Alembic/PostgreSQL y Celery/Redis para trabajo asíncrono. Esta decisión no cambia ese modelo.

## Decisión

Se incorpora un módulo de dominio `quotes` y un agregado persistente de comparativo, manteniendo las dependencias hacia adentro:

1. `Quote` protege la máquina de estados `received -> validating -> extracting -> extracted -> normalized -> pending_review -> approved/rejected -> included_in_comparison`.
2. El PDF de cotización reutiliza la validación y el almacenamiento privado existentes. La identidad de carga se protege con `(tender_id, supplier_id, file_hash)`.
3. La extracción se ejecuta por Celery mediante un puerto `QuoteAnalysisQueue`. Su idempotencia incluye hash del archivo, licitación, proveedor, versión del extractor, prompt, modelo y schema.
4. El adaptador IA existente se reutiliza con un prompt versionado `quote_extraction`; no se introduce un segundo proveedor o SDK solo para cotizaciones.
5. `QuoteExtractionRun` registra modelo, prompt/schema, extractor, tokens, costo estimado, resultado y errores. Cada `QuoteItem` conserva página, fragmento de evidencia y confianza.
6. La normalización hacia el catálogo es determinista y conservadora: solo se asocia un producto cuando existe una coincidencia exacta o una única coincidencia parcial no ambigua. Una asociación ausente no se inventa.
7. El comparativo es determinista. La configuración MVP fija usa cumplimiento técnico 50 %, precio 35 % y entrega 15 %. Los datos incompletos generan advertencias y una contribución neutral, no una inferencia automática.
8. La recomendación siempre incluye `human_review_required=true` y `decision=recommendation_only`. No adjudica ni ejecuta compras.
9. El comparativo se identifica con una clave derivada de licitación, snapshot de catálogo aprobado, versión de cotizaciones aprobadas y versión de scoring. Reintentar con la misma entrada reutiliza el resultado.
10. Las transiciones cruzadas de proveedor/RFQ/producto se encapsulan en reglas de dominio de la Iteración 9; los routers permanecen delgados.

## Consecuencias

### Positivas

- Completa el tramo RFQ -> cotización -> comparativo sin microservicios ni nueva tecnología.
- Mantiene trazabilidad de IA y de evidencia hasta el dato usado en la comparación.
- Los reintentos no duplican cotizaciones, extracciones ni comparativos.
- La recomendación es reproducible y explicable.
- El proveedor de IA puede cambiar detrás del puerto existente.

### Limitaciones aceptadas

- No hay OCR avanzado de cotizaciones.
- El matching catálogo/cotización no usa embeddings ni búsqueda semántica; los casos ambiguos quedan sin asociación automática.
- No hay scoring configurable por tenant o usuario; existe una sola versión MVP explícita.
- No existe adjudicación ni compra automática.

## Alternativas descartadas

- Crear un microservicio de cotizaciones: aumenta complejidad operativa sin necesidad para el MVP.
- Hacer que la IA calcule la recomendación: reduce reproducibilidad y explicabilidad.
- Tratar el resultado de IA como verdad: contradice la revisión humana y la trazabilidad requerida.
- Reutilizar `TenderDocument` como cotización sin contexto de proveedor: perdería identidad, estados e idempotencia propios del flujo comercial.
