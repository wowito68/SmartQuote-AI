# Validación de la Iteración 7

Este documento se completa con la ejecución final de GitHub Actions.

## Escenario reproducible

La prueba de integración utiliza un proveedor de búsqueda determinístico con tres resultados para un producto aprobado:

1. `Conductores del Centro SA de CV`, sitio `conductores.example.mx`, correo y teléfono.
2. Una segunda ficha del mismo dominio y contactos, procedente de otro directorio.
3. `Cables del Bajío`, sitio `cables-bajio.example.mx`, con formulario de contacto.

Resultado esperado:

- tres hallazgos crudos;
- dos proveedores maestros;
- un duplicado exacto consolidado sin borrar evidencia;
- tres fuentes;
- tres contactos únicos;
- dos asociaciones producto–proveedor;
- dos proveedores en `pending_review`;
- segunda solicitud reutilizada por idempotencia.

La prueba también valida aprobación, rechazo, edición, creación manual y fusión conservando historial.
