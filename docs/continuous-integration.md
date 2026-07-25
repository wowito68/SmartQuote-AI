# Integración continua

El workflow `.github/workflows/iteration-3-ci.yml` se ejecuta automáticamente en:

- cada `push` a cualquier rama, por lo que cada commit enviado a GitHub se valida;
- apertura, actualización, reapertura o paso a revisión de un pull request;
- ejecución manual mediante `workflow_dispatch`.

## Checks automáticos

1. **Code quality**: Ruff lint, Ruff format y compilación de fuentes Python.
2. **Unit tests**: pruebas unitarias de Domain y Application.
3. **Integration and API tests**: repositorios, migraciones y endpoints con PostgreSQL 16.
4. **Migration upgrade and rollback**: `upgrade head`, `downgrade base` y segundo `upgrade head`.
5. **Full test coverage**: suite completa con umbral mínimo de 90% y reporte XML descargable.
6. **OpenAPI contract**: confirma que las rutas y métodos públicos esperados permanezcan publicados.
7. **Docker image build**: valida que la imagen del backend pueda construirse.

Un commit que solo existe localmente no puede ser probado por GitHub. La ejecución comienza cuando el commit se publica mediante `push` o forma parte de una actualización de pull request.

El workflow evita filtros por rutas para que cambios en código, configuración o documentación se validen de la misma manera.
