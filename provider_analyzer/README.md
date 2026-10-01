# Provider Anomaly Analyzer

Motor autónomo de analítica de contratación pública y relaciones comprador–proveedor.

## Frontera con ATLAS AML

Este proyecto procesa datos intensivos de ChileCompra fuera de ATLAS. Ningún dataset bruto de licitaciones, órdenes, líneas o documentos se escribe en la base operacional de ATLAS. El contrato principal hacia Intelligence Fusion Layer es un export compacto `PROVIDER_ANALYZER_EXPORT_V1` con señales de revisión y trazabilidad.

Para consultas individuales de **Relación con el Estado**, ATLAS dispone además de un contrato histórico acotado por un único RUT y rango de años. Ese contrato consulta `provider_analyzer.supplier_year` a demanda y devuelve sólo resumen anual y compradores agregados; no replica el warehouse en la base operacional de ATLAS ni expone órdenes individuales.

Las señales son **priorización analítica**, no inferencias de delito, infracción ni lavado de activos. Todas las salidas conservan `semantic_class=INTEGRITY_REVIEW`, `scoring_eligible=false` y no modifican el score AML.

## Persistencia

La persistencia pesada vive en el proyecto Supabase `AML CLAUDE`, esquema privado `provider_analyzer`. Se guardan resúmenes mensuales comprador–proveedor, cobertura, eventos compactos de ruta, señales y evidencia. Los artefactos grandes usan el bucket privado `provider-analyzer-runtime`.

`supplier_year` mantiene el histórico anual compacto desde 2007. El núcleo Provider Analyzer sólo publica `provider_entity_history_v1`, ejecutable por `service_role`. La autenticación cruzada con ATLAS se implementa fuera del núcleo, en `integrations/atlas-provider-history`, para preservar el guardrail que impide introducir referencias del proyecto ATLAS dentro de `provider_analyzer`.

## Operación

- `provider-analyzer-backfill.yml`: backfill histórico controlado.
- `provider-entity-history.yml`: construye/persiste la historia anual compacta por proveedor.
- `provider-analyzer-monthly.yml`: procesa sólo el último mes completo (o un periodo solicitado), reutiliza histórico materializado y publica el export compacto.
- `provider-analyzer-ci.yml`: valida motor, contratos y guardrails.

## Contratos hacia ATLAS / Fusion

- Señales: `exports/provider_signals_v1.jsonl` + `exports/manifest.json`.
- Historia individual: `sql/provider_entity_history_v1.sql`.
- Bridge ATLAS (fuera del núcleo): `../integrations/atlas-provider-history/index.ts`.

Fusion puede cruzar señales con CGR, SII, UAF, sanciones y otras fuentes, pero no ejecuta el análisis masivo de compras públicas. La consulta histórica individual está limitada a un RUT y rango temporal por solicitud, preservando esta frontera de arquitectura.
