# Integración continua

El workflow valida:

1. resolución del lockfile, Ruff y compilación;
2. pruebas unitarias con Celery eager y broker en memoria;
3. pruebas de integración con PostgreSQL 16 y Redis 7;
4. worker Celery real y pipeline completo;
5. upgrade, downgrade y nuevo upgrade de Alembic;
6. cobertura mínima del 90%;
7. contrato OpenAPI de los endpoints de consulta;
8. construcción de la imagen Docker.

El lockfile resuelto se publica temporalmente como artifact durante el desarrollo de la iteración y se fija antes de cerrar el PR.

## Validaciones de la Iteración 6

El job de integración mantiene PostgreSQL 16 y Redis 7. La suite nueva prueba la cola `ai-extraction`, un worker Celery real y el flujo completo de catálogo, pero sustituye el proveedor OpenAI por una respuesta estructurada local. Ningún check de CI realiza llamadas facturables ni requiere una clave real.

El contrato OpenAPI verifica los cinco endpoints de catálogo y la cobertura mínima continúa en 90%.

## Validaciones de la Iteración 7

El contrato OpenAPI incluye los ocho endpoints de proveedores. La suite de integración valida el pipeline completo con un proveedor de búsqueda determinístico y un worker Celery real conectado a Redis. No se realizan búsquedas web ni llamadas externas durante CI.

Además se cubren persistencia de maestros globales, asociaciones por licitación, contactos, fuentes, matching, deduplicación, idempotencia, aprobación, rechazo, creación manual y fusión. El umbral global de cobertura continúa en 90%.
