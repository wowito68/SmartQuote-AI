# Iteracion 17 — Recomendacion determinista, explicable y human-gated

## Objetivo

Extender el flujo posterior al MVP desde el comparativo v2 hacia escenarios de recomendacion reproducibles sin convertir el sistema en un adjudicador automatico.

## Alcance implementado

- agregado `Recommendation` separado del comparativo;
- pesos explicitos de cumplimiento tecnico, precio y entrega;
- motor determinista sin OpenAI, FX ni datos inferidos;
- candidatos elegibles/inelegibles con razones de exclusion;
- scores componentes y total de 0 a 100 solo para candidatos elegibles;
- estados `ready` y `withheld`;
- empate superior retenido en lugar de desempate arbitrario;
- `human_review_required=true` como invariante de dominio y base de datos;
- idempotencia por comparativo, version de politica y pesos canonicos;
- historial de escenarios: cambiar pesos genera un escenario nuevo;
- auditoria `recommendation.created`, `recommendation.ready` y `recommendation.withheld`;
- API REST y UI dentro de la vista de Comparativo;
- migracion PostgreSQL `d9a7c41e6f20_recommendation_scenarios.py`.

## Contrato de datos

### Pesos

El backend no tiene pesos por defecto. Los tres pesos son requeridos, estan en `[0, 1]` y deben sumar 1.

La UI tampoco precarga pesos: los campos comienzan vacios y el boton solo se habilita cuando la suma visible es 100%.

### Elegibilidad

Para permanecer elegible un proveedor debe tener una oferta valida para cada producto y cantidad/unidad compatible.

Los criterios activos se validan de forma conservadora:

- tecnico activo: `compliant=1`, `partially_compliant=0.5`, `unknown` excluye y `non_compliant` excluye siempre;
- precio activo: el item debe ser monetariamente comparable y la oferta debe conservar total y moneda; no hay conversion FX;
- entrega activa: la entrega debe estar normalizada en dias.

Un criterio con peso cero no bloquea por ausencia de sus propios datos.

### Score

Para cada producto:

```text
technical_ratio = 1.0 o 0.5
price_ratio     = min_price / supplier_price
delivery_ratio  = min_days / supplier_days
```

Cada criterio se promedia sobre todos los productos. El score final es:

```text
100 * (
  technical_ratio * technical_weight
  + price_ratio * price_weight
  + delivery_ratio * delivery_weight
)
```

Los scores no existen para candidatos inelegibles; sus razones de exclusion se persisten en su lugar.

### Estado final

`ready` requiere un unico candidato elegible con score superior. `withheld` se utiliza si no hay candidatos elegibles o existe empate en el primer lugar.

`withheld` nunca contiene `recommended_supplier_id`.

## API

```text
POST /api/v1/comparisons/{comparison_id}/recommendations
GET  /api/v1/comparisons/{comparison_id}/recommendations
GET  /api/v1/recommendations/{recommendation_id}
```

El POST recibe:

```json
{
  "generated_by_user_id": "uuid",
  "technical_weight": 0.4,
  "price_weight": 0.4,
  "delivery_weight": 0.2
}
```

Los valores anteriores son solo un ejemplo de request; no son defaults de configuracion.

## Persistencia

La tabla `recommendations` conserva:

- `comparison_id` y `tender_id`;
- `recommendation_key`;
- `policy_version`;
- pesos exactos;
- usuario generador;
- estado;
- snapshot de candidatos y scores;
- proveedor recomendado opcional;
- explicacion;
- warnings;
- `human_review_required`;
- timestamp.

Constraint de unicidad:

```text
UNIQUE(comparison_id, recommendation_key)
```

## UI

La seccion aparece debajo de la matriz del comparativo y muestra:

- tres inputs de peso sin preset;
- suma visible y validacion 100%;
- resultado `ready` o `withheld`;
- explicacion;
- aviso explicito de revision humana;
- version de politica y huella del escenario;
- scores por proveedor;
- razones de exclusion.

La interfaz no ofrece una accion `Adjudicar` en esta iteracion.

## Adjudicacion y estado de licitacion

La generacion de escenarios no modifica `Tender.status`. Una licitacion en `comparison_ready` permanece en `comparison_ready`.

Aunque el dominio historico contiene el estado `awarded`, Iteracion 17 no lo utiliza. La adjudicacion requiere una iteracion separada con decision humana, autorizacion y auditoria propias.

## Compatibilidad

El `ComparisonEngine` legacy de Iteracion 9 permanece sin cambios por compatibilidad. Su recomendacion fija 50/35/15 no se usa en el nuevo motor y no se migra automaticamente.

## Costos externos

Costo incremental del motor de recomendacion:

```text
OpenAI: USD 0
Busqueda externa: USD 0
FX: USD 0
```

Toda la operacion utiliza datos ya persistidos en PostgreSQL.

## Validacion requerida antes del PR listo para revision

- Ruff global;
- Ruff format sobre Python tocado por Iteracion 17;
- migracion upgrade, rollback a `c8f3a05d6e94` y reapply;
- tests unitarios de dominio;
- tests unitarios del motor;
- integracion API/persistencia/auditoria/idempotencia;
- OpenAPI;
- frontend production build;
- SmartQuote CI global y cobertura >= 90%;
- regresiones de iteraciones previas.
