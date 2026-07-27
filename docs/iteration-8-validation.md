# Validación de la Iteración 8

## Escenario reproducible

La prueba de integración crea un catálogo aprobado y tres proveedores aprobados:

1. `Conductores del Centro`, con correo de ventas;
2. `Cables del Bajío`, sin correo público;
3. `Proveedor Manual`, con correo agregado por un usuario.

Se generan tres RFQs parametrizadas con un PDF adjunto. El resultado esperado es:

- tres borradores en `pending_review`;
- una RFQ identificada como proveedor sin correo;
- una segunda generación idéntica que reutiliza los tres borradores;
- edición de asunto, cuerpo y dos destinatarios antes de aprobar;
- bloqueo de modificaciones después de aprobar;
- una RFQ cancelada por falta de correo;
- dos RFQs enviadas;
- un fallo SMTP seguido por un reintento exitoso;
- tres `EmailMessage` y seis `OutboundMessageLog`;
- hash y tamaño del adjunto verificados antes del envío;
- todos los eventos de dominio y auditoría registrados.

El adaptador SMTP se sustituye por un doble determinístico que devuelve:

```text
provider_name = test-smtp
duration_ms = 37
external_message_id = <test-{attempt}@example.mx>
```

No se envían correos reales ni se utilizan credenciales externas durante las pruebas.

## Resultado local previo a CI

- 100 pruebas aprobadas;
- cobertura local: 90.51%, 6,553 de 7,240 líneas;
- migración `upgrade → downgrade → upgrade`: aprobada en SQLite;
- compilación Python: aprobada.

El resultado definitivo con PostgreSQL, Redis, Celery, Ruff, OpenAPI y Docker se registrará en el PR mediante GitHub Actions.

## Alcance confirmado

No se implementaron monitoreo del buzón, lectura de respuestas, análisis de cotizaciones ni comparativos.
