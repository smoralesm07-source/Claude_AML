# Provider Anomaly Analyzer

Motor autónomo de analítica de contratación pública y relaciones comprador–proveedor.

## Frontera con ATLAS AML

Este proyecto procesa datos intensivos de ChileCompra fuera de ATLAS. Ningún dataset bruto de licitaciones, órdenes, líneas o documentos se escribe en la base operacional de ATLAS. El único contrato hacia Intelligence Fusion Layer es un export compacto `PROVIDER_ANALYZER_EXPORT_V1` con señales de revisión y trazabilidad.

Las señales son **priorización analítica**, no inferencias de delito, infracción ni lavado de activos. Todas las salidas conservan `semantic_class=INTEGRITY_REVIEW`, `scoring_eligible=false` y no modifican el score AML.

## Persistencia

La persistencia pesada vive en el proyecto Supabase `AML CLAUDE`, esquema privado `provider_analyzer`. Se guardan resúmenes mensuales comprador–proveedor, cobertura, eventos compactos de ruta, señales y evidencia. Los artefactos grandes usan el bucket privado `provider-analyzer-runtime`.

## Operación

- `provider-analyzer-backfill.yml`: backfill histórico controlado, desde enero de 2024. No tiene cron.
- `provider-analyzer-monthly.yml`: procesa sólo el último mes completo (o un periodo solicitado), reutiliza histórico materializado y publica el export compacto.
- `provider-analyzer-ci.yml`: valida motor, contratos y guardrails.

## Contrato hacia Fusion

`exports/provider_signals_v1.jsonl` + `exports/manifest.json`.

Fusion puede cruzar estas señales con CGR, SII, UAF, sanciones y otras fuentes, pero no ejecuta el análisis masivo de compras públicas.