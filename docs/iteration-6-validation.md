# Validación de la Iteración 6

La validación automática de esta iteración comprueba:

- calidad estática con Ruff y compilación de fuentes;
- pruebas unitarias del dominio, normalizador y validación JSON;
- integración con PostgreSQL 16 y Redis 7;
- ejecución de la tarea Celery de catálogo con el proveedor OpenAI sustituido por un mock determinístico;
- ciclo completo de migraciones Alembic;
- cobertura mínima del 90%;
- contrato OpenAPI de los endpoints de catálogo;
- construcción reproducible de la imagen Docker mediante `uv sync --frozen`.

Las pruebas no realizan solicitudes reales a OpenAI ni generan costos externos. La integración del adaptador se valida con respuestas simuladas que conservan tokens, modelo, JSON estructurado y cálculo de costo.
