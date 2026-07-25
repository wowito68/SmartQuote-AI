# Integración continua

El workflow `.github/workflows/smartquote-ci.yml` se ejecuta automáticamente en:

- cada `push` a cualquier rama;
- apertura, actualización, reapertura o paso a revisión de un pull request;
- ejecución manual mediante `workflow_dispatch`.

## Checks automáticos

1. **Code quality**: Ruff lint, Ruff format y compilación de fuentes Python.
2. **Unit tests**: pruebas de Domain, Application, validación y almacenamiento.
3. **Integration and API tests**: repositorios, multipart, almacenamiento local y endpoints con PostgreSQL 16.
4. **Migration upgrade and rollback**: `upgrade head`, `downgrade base` y segundo `upgrade head`.
5. **Full test coverage**: suite completa con umbral mínimo de 90% y reporte XML descargable.
6. **OpenAPI contract**: confirma rutas de licitaciones, documentos, descarga y contrato multipart.
7. **Docker image build**: valida que la imagen del backend pueda construirse con el lockfile aprobado.

Los trabajos de integración usan directorios temporales privados para los documentos y eliminan los datos mediante fixtures de prueba.

Un commit local comienza a validarse cuando se publica mediante `push` o forma parte de una actualización de pull request.
