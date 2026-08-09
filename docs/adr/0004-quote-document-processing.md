# ADR-0004 — Procesamiento de documentos de cotización

- Estado: Aceptado
- Fecha: 2026-08-09
- Iteración: 12

## Contexto

SmartQuote AI recibe cotizaciones manualmente después de que un RFQ fue enviado. El repositorio ya tenía `Quote`, `QuoteExtractionRun`, `QuoteItem`, `FileStorage`, extractores PDF y `AIExtractionService`, pero el archivo estaba representado directamente por campos de `Quote`, la evidencia era un fragmento embebido en `QuoteItem` y el procesamiento de cotizaciones sólo aceptaba PDF.

La Iteración 12 necesita PDF, XLSX y DOCX, trazabilidad de cada extracción, reprocess versionado y revisión humana sin destruir el resultado original de IA.

## Decisión

### 1. `FileStorage` continúa siendo el almacenamiento

No se introduce otra abstracción de almacenamiento. `QuoteDocument` referencia la misma `storage_key` privada. La migración crea relaciones `QuoteDocument` para archivos históricos sin copiar los bytes.

### 2. `QuoteDocument` representa la relación de negocio

`QuoteDocument` almacena metadatos del archivo relacionados con una cotización: hash, tipo, MIME, tamaño, estado de procesamiento y versión/método de extractor. Los campos de archivo existentes en `Quote` se mantienen temporalmente como snapshot de compatibilidad con Iteración 9.

### 3. `QuoteExtractionRun` sigue siendo el tracking de IA

No se crea un tercer sistema de extracción. `QuoteExtractionRun` se amplía con `quote_document_id`, proveedor, nombre/versión del extractor, fingerprint, número de run, duración, reutilización y marca de run aprobado. Conserva modelo, prompt, schema, tokens, costo y errores.

El `ExtractionRun` de documentos de licitación no se reutiliza para este propósito porque está ligado por FK a `TenderDocument` y representa extracción textual, no análisis IA de una `Quote`.

### 4. Evidencia específica de cotizaciones

Se introduce `QuoteEvidenceReference`, porque `EvidenceReference` del catálogo está ligado a productos y extracciones del catálogo. La evidencia de cotización identifica:

- `Quote`;
- `QuoteDocument`;
- `QuoteExtractionRun`;
- entidad y campo;
- localizador (`page`, `sheet_row`, `paragraph`, `table_row`);
- fragmento fuente;
- método de extracción;
- estado `found/not_found/inferred/ambiguous`;
- confidence;
- timestamp.

El backend valida que un fragmento declarado como evidencia exista realmente en la sección fuente indicada.

### 5. PDF reutiliza los extractores existentes

PDF usa el `FallbackDocumentTextExtractor` existente (`PyMuPDF` + `pdfplumber`). No se agrega OCR avanzado.

### 6. XLSX y DOCX se leen con OOXML en modo datos

XLSX y DOCX son contenedores ZIP/XML. Para el alcance MVP se utiliza la biblioteca estándar de Python:

- no se ejecutan macros;
- se rechazan extensiones macro-enabled y formatos legacy;
- no se evalúan fórmulas XLSX;
- sólo se usan valores cacheados presentes como datos;
- no se resuelven vínculos externos;
- no se ejecuta contenido embebido.

Esto evita introducir dependencias adicionales cuando el alcance sólo requiere lectura estructurada.

### 7. Reprocess conserva historia

Una ejecución forzada genera un nuevo `QuoteExtractionRun`. Los `QuoteItem` del run anterior se marcan como no actuales; no se eliminan. Las evidencias y revisiones previas permanecen disponibles.

### 8. La IA no decide la aprobación

La IA extrae candidatos estructurados. Matching, normalización y compliance usan reglas deterministas. Los items críticos requieren revisión humana antes de que `Quote` llegue a `approved`.

## Alternativas consideradas

### Reutilizar `TenderDocument` para cotizaciones

Rechazado. Mezclaría documentos de licitación con respuestas de proveedor y haría ambigua la propiedad de los datos.

### Crear otro `FileStorage`

Rechazado. Duplicaría una responsabilidad ya resuelta.

### Usar `openpyxl` y `python-docx`

No seleccionado para este MVP. Ambas son opciones válidas si más adelante se requieren características Office más complejas. La lectura actual se puede resolver con OOXML sin ejecutar contenido ni agregar dependencias.

### Usar IA para matching final

Rechazado. La Iteración 12 requiere que la coincidencia sea explicable y revisable; la IA no se usa como fuente de verdad para el `product_id` definitivo.

## Consecuencias

- Se preserva compatibilidad con Iteración 9.
- La trazabilidad de quotes es explícita.
- Los formatos Office soportados son únicamente OOXML no macro: `.xlsx` y `.docx`.
- No hay conversión monetaria; monedas distintas siguen siendo no directamente comparables.
- La exactitud de XLSX/DOCX complejos se limita a datos textuales/tabulares disponibles en XML. Archivos con contenido no estándar deberán quedar fallidos/pendientes de intervención, no inferidos.
