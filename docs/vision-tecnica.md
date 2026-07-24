# SmartQuote AI - Documento técnico inicial

Estado: Propuesta para revisión  
Fecha: 2026-07-24  
Etapa: Diseño inicial, sin implementación de código

## 1. Visión general

SmartQuote AI es una plataforma para automatizar el proceso completo de compras asociado a licitaciones: análisis documental, extracción de productos, búsqueda de proveedores, solicitud de cotizaciones, seguimiento de respuestas, análisis comparativo y recomendación de la mejor opción.

El sistema no se limitará a enviar correos. Su valor central será convertir documentos no estructurados de licitación y respuestas de proveedores en información estructurada, trazable y accionable.

La primera versión debe priorizar:

- trazabilidad de cada decisión y dato extraído;
- revisión humana antes de acciones externas importantes;
- componentes desacoplados para cambiar proveedores de IA, correo y búsqueda;
- procesamiento asíncrono para tareas largas;
- arquitectura mantenible y testeable.

## 2. Alcance inicial

### Incluido

- Carga y administración de licitaciones.
- Carga de uno o varios PDF por licitación.
- Extracción de texto desde PDF.
- Extracción asistida por IA de productos y especificaciones.
- Catálogo estructurado de productos solicitados.
- Búsqueda de proveedores mediante una interfaz desacoplada.
- Registro de proveedores, contactos y fuentes.
- Aprobación manual de proveedores antes de enviar correos.
- Generación de correos personalizados.
- Envío por un proveedor de correo intercambiable.
- Registro de correos enviados y estado.
- Monitoreo de respuestas.
- Registro y descarga de archivos recibidos.
- Análisis de cotizaciones recibidas.
- Tabla comparativa y recomendación.

### Fuera del alcance de la primera versión

- Compras automáticas sin aprobación humana.
- Integraciones ERP complejas.
- Firma electrónica.
- Pagos.
- Negociación automática con proveedores.
- OCR avanzado para todos los documentos desde el inicio.
- Automatización multiempresa o multi-tenant completa, salvo que se decida explícitamente.

## 3. Requerimientos funcionales

### Licitaciones y documentos

- Crear, consultar, actualizar y cerrar licitaciones.
- Cargar múltiples documentos PDF por licitación.
- Registrar metadatos de documentos: nombre, tipo, tamaño, hash, fecha de carga y estado de procesamiento.
- Extraer texto de documentos digitales.
- Detectar si un PDF requiere OCR.
- Mantener historial de procesamiento y errores.

### Extracción de productos

- Identificar productos, cantidades, unidades, partidas y requisitos técnicos.
- Asociar especificaciones a cada producto.
- Registrar confianza de extracción y fuente documental.
- Permitir revisión y corrección manual.

### Catálogo estructurado

- Construir un catálogo por licitación.
- Agrupar productos equivalentes o similares cuando aplique.
- Mantener versiones o cambios relevantes después de revisión humana.

### Proveedores

- Buscar proveedores candidatos en Internet.
- Guardar sitio web, razón social, país, ubicación y fuente.
- Extraer contactos: correo, teléfono, WhatsApp, nombre de contacto y cargo cuando exista.
- Asociar proveedores a productos o familias de productos.
- Permitir aprobación, rechazo o descarte.

### Correos

- Generar correos personalizados por proveedor.
- Adjuntar documentos relevantes.
- Enviar solicitudes de cotización usando un proveedor desacoplado.
- Registrar asunto, destinatarios, cuerpo, adjuntos, estado, proveedor técnico y errores.
- Soportar plantillas editables en iteraciones posteriores.

### Respuestas y cotizaciones

- Monitorear buzones o hilos de correo.
- Asociar respuestas a licitaciones, proveedores y solicitudes enviadas.
- Descargar archivos adjuntos.
- Extraer precios, monedas, tiempos de entrega, marcas, modelos, garantías y condiciones comerciales.
- Registrar valores extraídos con confianza y fuente.

### Comparativo y recomendación

- Generar tabla comparativa por producto y proveedor.
- Considerar criterios como precio, tiempo de entrega, cumplimiento técnico, condiciones comerciales y confiabilidad.
- Explicar la recomendación generada.
- Permitir aprobación o ajuste manual.

### Usuarios, tareas y auditoría

- Gestionar usuarios.
- Registrar acciones importantes.
- Registrar tareas asíncronas y su estado.
- Mantener logs de negocio para auditoría.

## 4. Requerimientos no funcionales

- Mantenibilidad: arquitectura por capas, bajo acoplamiento y dependencias explícitas.
- Testeabilidad: lógica de dominio y casos de uso independientes de frameworks.
- Escalabilidad: tareas pesadas fuera del ciclo HTTP mediante Celery.
- Observabilidad: logs estructurados, estados de tarea y errores consultables.
- Seguridad: validación de archivos, control de acceso, protección de credenciales y secretos fuera del repositorio.
- Trazabilidad: cada extracción debe vincularse al documento, página o fuente.
- Resiliencia: reintentos controlados para correo, búsqueda, IA y procesamiento documental.
- Privacidad: minimizar datos enviados a servicios externos y registrar qué información se envía.
- Idempotencia: evitar envíos duplicados de correos y reprocesamientos inconsistentes.
- Portabilidad: adaptadores para cambiar OpenAI, SMTP, Gmail API, Microsoft Graph o motor de búsqueda.

## 5. Arquitectura propuesta

Se propone Clean Architecture con separación estricta entre reglas de negocio, casos de uso, infraestructura y API.

### Capas

#### Domain

Contiene entidades, value objects, reglas de negocio puras, contratos de repositorio y eventos de dominio. No depende de FastAPI, SQLAlchemy, OpenAI, Celery ni servicios externos.

Responsabilidades:

- modelar licitaciones, productos, proveedores, contactos, correos y cotizaciones;
- validar invariantes de negocio;
- definir estados permitidos;
- definir interfaces requeridas por la aplicación.

#### Application

Contiene casos de uso y orquestación. Depende del dominio y de puertos abstractos, pero no de implementaciones externas.

Responsabilidades:

- procesar documentos;
- extraer productos;
- buscar proveedores;
- aprobar proveedores;
- generar y enviar solicitudes;
- monitorear respuestas;
- analizar cotizaciones;
- generar comparativos.

#### Infrastructure

Contiene implementaciones concretas de persistencia, IA, correo, búsqueda, almacenamiento de archivos, OCR y cola de tareas.

Responsabilidades:

- repositorios SQLAlchemy;
- clientes de OpenAI;
- adaptadores SMTP, Gmail API o Microsoft Graph;
- adaptadores de búsqueda;
- procesamiento con PyMuPDF, pdfplumber y OCR;
- workers Celery;
- integración con PostgreSQL y Redis.

#### API

Expone endpoints HTTP con FastAPI. Debe ser delgada: valida entrada, llama casos de uso y devuelve DTOs.

Responsabilidades:

- rutas;
- esquemas de request y response;
- autenticación y autorización;
- manejo de errores HTTP;
- inyección de dependencias.

#### Services

Servicios transversales o de aplicación que no pertenecen a infraestructura pura ni al dominio central. Deben mantenerse pequeños.

Ejemplos:

- generación de prompts;
- normalización de unidades;
- scoring de proveedores;
- scoring de cotizaciones;
- construcción de tablas comparativas.

## 6. Módulos iniciales

- `tenders`: licitaciones y estado general del proceso.
- `documents`: carga, almacenamiento, extracción de texto y trazabilidad.
- `catalog`: productos, partidas y especificaciones.
- `suppliers`: proveedores, contactos, fuentes y aprobación.
- `outreach`: generación y envío de correos.
- `inbox`: monitoreo de respuestas y adjuntos.
- `quotes`: cotizaciones recibidas y extracción de datos.
- `comparison`: tabla comparativa y recomendación.
- `users`: usuarios y permisos.
- `tasks`: tareas asíncronas y reintentos.
- `audit`: logs de negocio y eventos.
- `ai`: puertos y servicios de IA.
- `search`: puertos y servicios de búsqueda.
- `email`: puertos y servicios de correo.

## 7. Casos de uso

### CU-01 Crear licitación

Actor: usuario.  
Resultado: licitación creada en estado `draft`.

### CU-02 Cargar documentos

Actor: usuario.  
Resultado: documentos asociados, validados y pendientes de procesamiento.

### CU-03 Procesar documentos

Actor: sistema.  
Resultado: texto extraído, páginas indexadas y errores registrados si aplica.

### CU-04 Extraer productos y especificaciones

Actor: sistema con IA.  
Resultado: productos y especificaciones candidatos con nivel de confianza.

### CU-05 Revisar catálogo

Actor: usuario.  
Resultado: productos aprobados, editados o descartados.

### CU-06 Buscar proveedores

Actor: sistema.  
Resultado: proveedores candidatos vinculados a productos.

### CU-07 Revisar proveedores

Actor: usuario.  
Resultado: proveedores aprobados o rechazados.

### CU-08 Generar solicitudes de cotización

Actor: sistema.  
Resultado: borradores de correo por proveedor.

### CU-09 Enviar solicitudes

Actor: usuario/sistema según permisos.  
Resultado: correos enviados y estados registrados.

### CU-10 Monitorear respuestas

Actor: sistema.  
Resultado: respuestas y adjuntos asociados a la licitación.

### CU-11 Analizar cotizaciones

Actor: sistema con IA.  
Resultado: precios, tiempos, marcas, modelos y condiciones extraídas.

### CU-12 Generar comparativo

Actor: sistema.  
Resultado: tabla comparativa por producto y proveedor.

### CU-13 Recomendar mejor opción

Actor: sistema con revisión humana.  
Resultado: recomendación explicada y auditable.

## 8. Entidades iniciales

### User

- `id`
- `email`
- `full_name`
- `role`
- `is_active`
- `created_at`
- `updated_at`

### Tender

- `id`
- `title`
- `description`
- `status`
- `deadline`
- `created_by_user_id`
- `created_at`
- `updated_at`

Estados sugeridos: `draft`, `documents_uploaded`, `processing`, `catalog_review`, `supplier_search`, `supplier_review`, `rfq_sending`, `waiting_quotes`, `quote_analysis`, `comparison_ready`, `closed`, `cancelled`.

### TenderDocument

- `id`
- `tender_id`
- `file_name`
- `file_path`
- `mime_type`
- `file_size`
- `file_hash`
- `document_type`
- `processing_status`
- `requires_ocr`
- `uploaded_by_user_id`
- `created_at`
- `updated_at`

### DocumentPage

- `id`
- `document_id`
- `page_number`
- `text`
- `extraction_method`
- `confidence`

### Product

- `id`
- `tender_id`
- `line_item_number`
- `name`
- `description`
- `quantity`
- `unit`
- `category`
- `status`
- `confidence`
- `source_document_id`
- `source_page`
- `created_at`
- `updated_at`

### ProductSpecification

- `id`
- `product_id`
- `name`
- `value`
- `unit`
- `is_required`
- `confidence`
- `source_document_id`
- `source_page`

### Supplier

- `id`
- `legal_name`
- `trade_name`
- `website`
- `country`
- `city`
- `status`
- `source`
- `notes`
- `created_at`
- `updated_at`

Estados sugeridos: `candidate`, `approved`, `rejected`, `inactive`.

### SupplierContact

- `id`
- `supplier_id`
- `name`
- `role`
- `email`
- `phone`
- `whatsapp`
- `source_url`
- `confidence`
- `created_at`
- `updated_at`

### ProductSupplierMatch

- `id`
- `product_id`
- `supplier_id`
- `match_score`
- `status`
- `source_url`
- `reason`
- `created_at`

### SentEmail

- `id`
- `tender_id`
- `supplier_id`
- `contact_id`
- `provider`
- `external_message_id`
- `subject`
- `body`
- `status`
- `sent_at`
- `error_message`
- `created_by_user_id`
- `created_at`

Estados sugeridos: `draft`, `queued`, `sent`, `failed`, `bounced`, `responded`.

### EmailAttachment

- `id`
- `email_id`
- `document_id`
- `file_name`
- `file_path`
- `mime_type`

### Quote

- `id`
- `tender_id`
- `supplier_id`
- `status`
- `currency`
- `total_amount`
- `delivery_time_days`
- `commercial_terms`
- `valid_until`
- `received_at`
- `created_at`
- `updated_at`

### QuoteItem

- `id`
- `quote_id`
- `product_id`
- `brand`
- `model`
- `unit_price`
- `quantity`
- `total_price`
- `delivery_time_days`
- `compliance_status`
- `notes`
- `confidence`

### ReceivedFile

- `id`
- `tender_id`
- `supplier_id`
- `quote_id`
- `source_email_id`
- `file_name`
- `file_path`
- `mime_type`
- `file_hash`
- `processing_status`
- `created_at`

### TaskRecord

- `id`
- `task_type`
- `status`
- `entity_type`
- `entity_id`
- `attempts`
- `last_error`
- `started_at`
- `finished_at`
- `created_at`

### AuditLog

- `id`
- `actor_user_id`
- `action`
- `entity_type`
- `entity_id`
- `metadata`
- `created_at`

## 9. Relaciones principales

- Un `User` crea muchas `Tender`.
- Una `Tender` tiene muchos `TenderDocument`.
- Un `TenderDocument` tiene muchas `DocumentPage`.
- Una `Tender` tiene muchos `Product`.
- Un `Product` tiene muchas `ProductSpecification`.
- Un `Supplier` tiene muchos `SupplierContact`.
- Un `Product` puede relacionarse con muchos `Supplier` mediante `ProductSupplierMatch`.
- Una `Tender` tiene muchos `SentEmail`.
- Un `SentEmail` pertenece a un `Supplier` y opcionalmente a un `SupplierContact`.
- Un `SentEmail` tiene muchos `EmailAttachment`.
- Una `Tender` recibe muchas `Quote`.
- Una `Quote` pertenece a un `Supplier`.
- Una `Quote` tiene muchos `QuoteItem`.
- Un `QuoteItem` corresponde a un `Product`.
- Una `ReceivedFile` puede estar asociada a una `Quote`.
- `TaskRecord` puede apuntar a cualquier entidad procesable mediante `entity_type` y `entity_id`.
- `AuditLog` registra acciones sobre entidades relevantes.

## 10. Flujo completo del sistema

1. El usuario crea una licitación.
2. El usuario carga uno o varios PDF.
3. El sistema valida archivos, calcula hash y registra documentos.
4. El sistema agenda tareas de extracción de texto.
5. El extractor intenta obtener texto con PyMuPDF o pdfplumber.
6. Si el texto es insuficiente, marca el documento como candidato a OCR.
7. El sistema envía el texto estructurado al servicio de IA para identificar productos y especificaciones.
8. Los productos candidatos quedan disponibles para revisión.
9. El usuario aprueba, edita o descarta productos.
10. El sistema busca proveedores por producto, categoría y especificaciones clave.
11. El sistema registra proveedores, contactos y fuentes.
12. El usuario aprueba proveedores.
13. El sistema genera borradores de solicitudes de cotización.
14. El usuario revisa y autoriza el envío.
15. El sistema envía correos, adjunta documentos y registra estados.
16. El sistema monitorea respuestas.
17. El sistema descarga adjuntos y los vincula con proveedor y licitación.
18. El sistema analiza cotizaciones con extracción documental e IA.
19. El sistema normaliza moneda, cantidades, unidades y tiempos.
20. El sistema genera tabla comparativa.
21. El sistema calcula recomendación y explica criterios.
22. El usuario revisa el resultado y decide la compra.

## 11. Riesgos y mitigaciones

### Extracción imperfecta desde PDF

Riesgo: documentos escaneados, tablas complejas o baja calidad.  
Mitigación: detección temprana de OCR, trazabilidad por página, revisión humana y niveles de confianza.

### Alucinaciones o errores de IA

Riesgo: productos o condiciones inventadas.  
Mitigación: prompts con formato estricto, validación contra fuentes, salida estructurada, confidence score y aprobación humana.

### Datos de proveedores desactualizados

Riesgo: contactos incorrectos o fuentes no confiables.  
Mitigación: guardar fuente URL, fecha de consulta, score de confianza y validación manual.

### Envío duplicado de correos

Riesgo: solicitudes repetidas al mismo proveedor.  
Mitigación: idempotency keys, estados de envío, restricciones únicas y auditoría.

### Bloqueos por proveedores de correo

Riesgo: límites SMTP, Gmail o Microsoft Graph.  
Mitigación: colas, rate limiting, reintentos y proveedor intercambiable.

### Costos de IA

Riesgo: procesamiento caro en documentos grandes.  
Mitigación: segmentación, caché de extracciones, modelos adecuados por tarea y límites por licitación.

### Seguridad de documentos sensibles

Riesgo: exposición de información confidencial.  
Mitigación: control de acceso, almacenamiento seguro, secretos fuera del repositorio y logging sin datos sensibles.

## 12. Dependencias propuestas

### Backend

- Python 3.12
- FastAPI
- Pydantic
- SQLAlchemy
- Alembic
- PostgreSQL
- Celery
- Redis, si se requiere broker/result backend
- PyMuPDF
- pdfplumber
- OpenAI Python SDK
- pytest
- ruff
- mypy, opcional desde una iteración temprana

### Frontend

- React
- TypeScript
- TailwindCSS
- Vite
- React Query o TanStack Query
- React Hook Form
- Zod

### Infraestructura local

- Docker Compose para PostgreSQL, Redis y servicios locales.
- Variables de entorno para credenciales.
- Migraciones con Alembic.

## 13. Estructura de carpetas recomendada

```text
SmartQuote-AI/
  backend/
    app/
      domain/
        tenders/
        documents/
        catalog/
        suppliers/
        outreach/
        quotes/
        users/
        shared/
      application/
        use_cases/
        ports/
        dto/
      infrastructure/
        database/
        document_processing/
        ai/
        search/
        email/
        storage/
        tasks/
      api/
        routes/
        schemas/
        dependencies/
        middleware/
      services/
      config/
      main.py
    tests/
      unit/
      integration/
    alembic/
    pyproject.toml
  frontend/
    src/
      app/
      features/
        tenders/
        documents/
        catalog/
        suppliers/
        outreach/
        quotes/
        comparison/
      shared/
        components/
        hooks/
        api/
        types/
      main.tsx
    package.json
  docs/
    vision-tecnica.md
    adr/
  docker-compose.yml
  README.md
```

## 14. Principios de diseño

- La API no contiene reglas de negocio.
- Los casos de uso orquestan, pero no conocen detalles de infraestructura.
- Los adaptadores externos implementan puertos definidos por la aplicación.
- El dominio no importa librerías externas de frameworks.
- Todo proceso largo debe poder ejecutarse de forma asíncrona.
- Toda acción externa importante debe ser auditable.
- Toda extracción automática debe poder ser revisada por una persona.
- El sistema debe permitir cambiar IA, búsqueda o correo con impacto limitado.

## 15. Puertos iniciales

- `DocumentTextExtractor`: extrae texto y metadatos desde documentos.
- `OCRService`: procesa documentos escaneados cuando sea necesario.
- `AIExtractionService`: extrae productos, especificaciones y cotizaciones.
- `SupplierSearchService`: busca proveedores candidatos.
- `ContactDiscoveryService`: obtiene contactos desde fuentes públicas o APIs.
- `EmailComposer`: genera borradores personalizados.
- `EmailSender`: envía correos mediante proveedor configurable.
- `InboxReader`: monitorea respuestas.
- `FileStorage`: guarda y recupera documentos.
- `TaskQueue`: agenda tareas en segundo plano.
- `AuditLogger`: registra acciones de negocio.

## 16. Backlog inicial

### Iteración 0 - Base documental y decisiones

- Aprobar documento técnico inicial.
- Crear ADR base.
- Definir convenciones de arquitectura.
- Definir alcance del MVP.

### Iteración 1 - Scaffold backend

- Crear proyecto FastAPI.
- Configurar `pyproject.toml`.
- Configurar settings por entorno.
- Agregar health check.
- Configurar ruff y pytest.

### Iteración 2 - Base de datos

- Configurar SQLAlchemy.
- Configurar Alembic.
- Crear modelos iniciales.
- Crear primera migración.
- Preparar PostgreSQL local con Docker Compose.

### Iteración 3 - Licitaciones y documentos

- CRUD inicial de licitaciones.
- Carga de documentos.
- Almacenamiento local desacoplado.
- Registro de documentos y estados.

### Iteración 4 - Extracción de texto

- Integrar PyMuPDF/pdfplumber.
- Guardar páginas extraídas.
- Detectar documentos candidatos a OCR.
- Ejecutar procesamiento asíncrono.

### Iteración 5 - Extracción IA de productos

- Diseñar prompt y salida estructurada.
- Implementar adaptador OpenAI.
- Guardar productos y especificaciones candidatos.
- Agregar revisión manual básica.

### Iteración 6 - Proveedores

- Diseñar puerto de búsqueda.
- Implementar primer adaptador de búsqueda.
- Registrar proveedores, contactos y fuentes.
- Flujo de aprobación.

### Iteración 7 - Solicitudes por correo

- Diseñar puerto de correo.
- Generar borradores.
- Enviar correos con proveedor inicial.
- Registrar estados y errores.

### Iteración 8 - Monitoreo de respuestas

- Leer respuestas del proveedor configurado.
- Descargar adjuntos.
- Asociar archivos con licitación y proveedor.

### Iteración 9 - Análisis de cotizaciones

- Extraer datos de cotización.
- Guardar cotizaciones e items.
- Normalizar moneda, unidades y tiempos.

### Iteración 10 - Comparativo

- Construir tabla comparativa.
- Calcular score.
- Generar recomendación explicada.

### Iteración 11 - Frontend MVP

- Crear interfaz de licitaciones.
- Carga de documentos.
- Revisión de catálogo.
- Revisión de proveedores.
- Visualización de comparativo.

## 17. Roadmap de desarrollo

### Fase 1 - Fundaciones

Objetivo: dejar backend, base de datos, arquitectura y flujo documental funcionando.

Entregables:

- FastAPI inicial.
- PostgreSQL y Alembic.
- Entidades principales.
- Carga y procesamiento de documentos.
- Extracción básica de texto.

### Fase 2 - Inteligencia documental

Objetivo: extraer productos y especificaciones con IA, con revisión humana.

Entregables:

- Adaptador OpenAI.
- Prompts versionados.
- Productos candidatos.
- Especificaciones trazables.

### Fase 3 - Proveedores y outreach

Objetivo: encontrar proveedores, aprobarlos y enviar solicitudes.

Entregables:

- Capa de búsqueda desacoplada.
- Registro de proveedores y contactos.
- Generación de correos.
- Envío y tracking.

### Fase 4 - Recepción y análisis

Objetivo: procesar respuestas y cotizaciones.

Entregables:

- Monitoreo de inbox.
- Descarga de adjuntos.
- Extracción de datos comerciales.
- Cotizaciones estructuradas.

### Fase 5 - Comparativo y recomendación

Objetivo: apoyar la decisión de compra.

Entregables:

- Tabla comparativa.
- Scoring configurable.
- Recomendación explicada.
- Exportación futura a Excel/PDF.

### Fase 6 - Endurecimiento

Objetivo: preparar el sistema para uso real.

Entregables:

- Seguridad.
- Roles y permisos.
- Observabilidad.
- Manejo robusto de errores.
- Pruebas de integración.
- Optimización de costos IA.

## 18. Decisiones pendientes

- ¿El MVP será single-tenant o multi-tenant?
- ¿El primer proveedor de correo será SMTP, Gmail API o Microsoft Graph?
- ¿El primer almacenamiento de archivos será local o S3-compatible?
- ¿Se requiere autenticación desde la primera iteración o se posterga tras el flujo principal?
- ¿Qué motor/API de búsqueda se usará primero?
- ¿Qué nivel de explicación necesita la recomendación final?
- ¿Habrá exportación a Excel desde el MVP?

## 19. Criterios de aprobación de esta etapa

Esta etapa se considera aprobada cuando:

- el alcance inicial resulta claro;
- las entidades principales cubren el proceso completo;
- la arquitectura propuesta es aceptada;
- el backlog incremental está alineado con prioridades del producto;
- se autoriza explícitamente iniciar la Iteración 1.

