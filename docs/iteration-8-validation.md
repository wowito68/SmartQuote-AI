# Validación de la Iteración 8

## Resultado final

La ejecución definitiva de GitHub Actions se realizó sobre la rama
`agent/iteration-8-rfq-email-delivery` con PostgreSQL 16 y Redis 7.

Los siete trabajos terminaron correctamente:

- Ruff lint y compilación Python;
- pruebas unitarias;
- pruebas de integración, API y Celery;
- ciclo Alembic `upgrade → downgrade → upgrade`;
- cobertura completa con umbral mínimo de 90%;
- contrato OpenAPI;
- construcción de la imagen Docker con dependencias congeladas.

La suite completa contiene **100 pruebas aprobadas**. La cobertura alcanzada fue
de **90.76%**: 6,570 de 7,239 líneas.

## Escenario reproducible

La prueba de integración crea un catálogo aprobado y tres proveedores aprobados:

1. `Conductores del Centro`, con correo de ventas;
2. `Cables del Bajío`, sin correo público;
3. `Proveedor Manual`, con correo agregado por un usuario.

Se generan tres RFQs parametrizadas con un PDF adjunto. El resultado obtenido es:

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

Métricas del escenario:

- RFQs generadas: 3;
- RFQs enviadas: 2;
- RFQs canceladas: 1;
- intentos fallidos: 1;
- reintentos: 1;
- porcentaje de éxito de RFQs: 66.67%;
- destinatarios del envío múltiple: 2;
- duración simulada por intento SMTP: 37 ms.

No se envían correos reales ni se utilizan credenciales externas durante las
pruebas. La duración simulada valida persistencia y observabilidad, pero no debe
interpretarse como un benchmark de una red o proveedor SMTP real.

## Alcance confirmado

No se implementaron monitoreo del buzón, lectura de respuestas, análisis de
cotizaciones ni comparativos.
