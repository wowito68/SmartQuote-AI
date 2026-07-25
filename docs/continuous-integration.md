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
