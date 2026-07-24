# ADR 0001 - Arquitectura base de SmartQuote AI

Estado: Propuesto  
Fecha: 2026-07-24

## Contexto

SmartQuote AI debe automatizar un proceso de compras completo que incluye documentos, IA, búsqueda web, correo, recepción de archivos, análisis de cotizaciones y recomendación. El sistema tendrá integraciones externas que pueden cambiar con el tiempo: OpenAI, proveedores de correo, motores de búsqueda, OCR y almacenamiento.

Necesitamos una arquitectura que permita evolucionar por iteraciones sin acoplar la lógica de negocio a frameworks o proveedores concretos.

## Decisión

Usaremos Clean Architecture con las siguientes capas principales:

- `domain`: entidades, value objects, reglas de negocio y contratos.
- `application`: casos de uso, puertos y DTOs.
- `infrastructure`: implementaciones concretas de base de datos, IA, búsqueda, correo, almacenamiento y tareas.
- `api`: FastAPI, rutas, schemas, dependencias y errores HTTP.
- `services`: servicios auxiliares de aplicación, como scoring, normalización y construcción de prompts.

Los proveedores externos se integrarán mediante puertos:

- IA mediante `AIExtractionService`.
- Búsqueda mediante `SupplierSearchService`.
- Correo mediante `EmailSender` e `InboxReader`.
- Archivos mediante `FileStorage`.
- Tareas mediante `TaskQueue`.

## Justificación

Esta decisión permite:

- probar casos de uso sin depender de FastAPI, SQLAlchemy o APIs externas;
- cambiar proveedores de IA, correo o búsqueda con menor impacto;
- mantener reglas de negocio en una capa estable;
- evolucionar el sistema por iteraciones;
- registrar decisiones técnicas y riesgos desde el inicio.

## Consecuencias

### Positivas

- Bajo acoplamiento.
- Mejor mantenibilidad.
- Mayor facilidad para pruebas unitarias.
- Integraciones externas reemplazables.
- Separación clara entre negocio e infraestructura.

### Costos

- Más estructura inicial que una aplicación CRUD simple.
- Requiere disciplina para evitar lógica de negocio en rutas o adaptadores.
- Puede sentirse más lento al inicio, aunque reduce deuda técnica en fases posteriores.

## Alternativas consideradas

### Arquitectura monolítica por módulos FastAPI

Ventaja: velocidad inicial.  
Desventaja: alto riesgo de acoplar reglas de negocio, persistencia e integraciones externas.

### Microservicios desde el inicio

Ventaja: separación operativa.  
Desventaja: sobreingeniería para la etapa inicial, mayor complejidad de despliegue y observabilidad.

## Resultado esperado

El proyecto iniciará como un monolito modular con Clean Architecture. Si el producto crece, algunos módulos podrán extraerse posteriormente a servicios separados, pero solo cuando exista una necesidad real de escalado, despliegue independiente o aislamiento operativo.

