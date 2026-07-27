# Validación de la Iteración 7

## Resultado final

La ejecución definitiva de GitHub Actions se realizó sobre la rama
`agent/iteration-7-supplier-discovery` con PostgreSQL 16 y Redis 7.

Los siete trabajos terminaron correctamente:

- Ruff lint y compilación Python;
- pruebas unitarias;
- pruebas de integración, API y Celery;
- ciclo Alembic `upgrade → downgrade → upgrade`;
- cobertura completa con umbral mínimo de 90%;
- contrato OpenAPI;
- construcción de la imagen Docker con dependencias congeladas.

La cobertura alcanzada fue de **90.68%**: 5,188 de 5,721 líneas.

## Escenario reproducible

La prueba de integración utiliza un proveedor de búsqueda determinístico con tres
resultados para un producto aprobado:

1. `Conductores del Centro SA de CV`, sitio `conductores.example.mx`, correo y
   teléfono.
2. Una segunda ficha del mismo dominio y contactos, procedente de otro
   directorio.
3. `Cables del Bajío`, sitio `cables-bajio.example.mx`, con formulario de
   contacto.

Resultado obtenido:

- tres hallazgos crudos;
- dos proveedores maestros;
- un duplicado exacto consolidado sin borrar evidencia;
- tres fuentes trazables;
- tres contactos únicos;
- dos asociaciones producto–proveedor;
- dos proveedores en `pending_review`;
- 100% de proveedores con al menos un contacto válido;
- segunda solicitud reutilizada por idempotencia.

El matching del proveedor conductor produce un score superior a 40/100 y
conserva los cuatro componentes y razones del algoritmo. El score no aprueba al
proveedor: únicamente ordena la evidencia para revisión humana.

La prueba también valida aprobación, rechazo, edición, creación manual y fusión
conservando el proveedor maestro, la asociación por licitación, fuentes,
contactos, revisiones y auditoría.

## Alcance confirmado

No se implementaron RFQs, envío de correos, monitoreo de respuestas ni análisis
de cotizaciones.
