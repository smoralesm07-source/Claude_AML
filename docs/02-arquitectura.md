# IFL Cockpit v1 · Arquitectura propuesta

Propuesta de evolución del prototipo `cockpit.html` (v0.6, datos incrustados) hacia una
aplicación **gobernada por contrato** que consume los siete radares del ecosistema.

## 1. Principio rector

> El cockpit **no calcula riesgo**. Proyecta señales que los radares ya produjeron, mide su
> propia maquinaria y registra qué hizo el analista con cada una.

Consecuencia de diseño: el cockpit no contiene reglas de negocio AML. Si una cifra aparece en
pantalla, existe un archivo de un radar que la respalda y un `evidence_ref` que la traza.

## 2. Posición en el ecosistema

```
Radar SII ─┐
Radar UAF ─┤
Radar CGR ─┤   interop/integration_manifest_v1.json
Radar Del. ─┼─► docs/data/*_fusion_v1.jsonl ──► Intelligence Fusion Layer ──► IFL Cockpit
Presup.Ab. ─┤   docs/data/fusion_interop_status_v1.json      (fusión)          (esta app)
Sanciones ─┤
Radar OSFL ─┘
Context Hub ────► territory_id / sector_id conformados ──────────┘
```

Los siete manifiestos declaran `canonical_consumer: smoralesm07-source/Intelligence_Fusion_Layer`.
El cockpit es la **capa de presentación** de ese consumidor: lee un único artefacto,
`cockpit_contract_v1.json`, y nada más.

### Estado real de los radares (leído de sus manifiestos)

| Radar | `implementation_stage` | Identidad | Territorio | Sector |
|---|---|---|---|---|
| SII | `FUSION_CONTRACT_READY_NATIVE_PARQUET` | `NATIVE_INTEROP_READY` | `ADAPTER_PARTIAL` | referencia |
| UAF | `FUSION_EXPORT_READY` | `ADAPTER_READY` | no primaria | nativo UAF |
| CGR | `FUSION_EXPORT_READY_TERRITORY_PARTIAL` | `ADAPTER_READY` | `ADAPTER_PARTIAL` | referencia |
| Delictual | `FUSION_EXPORT_READY_TERRITORY_CONTEXT` | no primaria | `ADAPTER_READY` | — |
| Presupuesto | `ADAPTER_PARTIAL` | `NATIVE_TRANSACTION_INTEROP_READY` | `ADAPTER_PARTIAL` | vía entidad |
| Sanciones | `FUSION_EXPORT_READY` | `ADAPTER_READY` | no primaria | vía entidad |
| OSFL | `ADAPTER_READY_WITH_TERRITORY_PARTIAL` | `ADAPTER_READY` | `ADAPTER_PARTIAL` | taxonomía OSFL |
| Context Hub | `OPERATIONAL_V0_2_1` | — | 16/56/346 CUT | 55 sectores UAF |

Esta tabla **es** el módulo *Salud del Programa*: se renderiza desde los manifiestos, no se
escribe a mano.

## 3. Diferencias contra la v0.6

| | v0.6 (`cockpit.html`) | v1 (`app/`) |
|---|---|---|
| Datos | 6 arreglos JS incrustados | `data/cockpit_contract_v1.json` validado contra esquema |
| Módulos | 10 | 14 (+ Salud, + Casos, + Benchmark, + Calibración) |
| Hallazgo | Tarjeta sin estado | Caso con estado, SLA, responsable y disposición |
| Personas | 1 modo | 4 perfiles que reordenan la navegación |
| Autoobservación | ninguna | 14 KPI de programa con umbral y tendencia |
| Denominador externo | ninguno | series ROS/ROE UAF publicadas |
| Guardrails | texto fijo en la vista | catálogo con `scope`, inyectado por módulo |
| Código | 980 líneas monolito | HTML + CSS + 2 módulos JS |

## 4. Módulos

### Grupo A — Exploración *(qué mirar primero)*
1. **Motor de Hallazgos** — cola de prioridad por convergencia de señales independientes.
2. **Territorio** — mapa de 16 regiones, capas conmutables, detalle por región.
3. **Actividad Sectorial** — 55 actividades UAF, universo inscrito real y crosswalk UAF↔ACTECO.
4. **Anomalías** — patrones contextuales que aún **no** son señal AML gobernada.

### Grupo B — Investigación *(qué hacer con lo que miro)* — **nuevo**
5. **Casos** — cola con estado, antigüedad, SLA, responsable, disposición tipificada.
6. **AML 360°** — vista integrada por entidad.
7. **Red de Relaciones** — vínculos observados, sin herencia de riesgo.
8. **Evidencia** — matriz de cobertura, claves conformadas, linaje.

### Grupo C — Supervisión *(cómo funciona el sistema)* — **nuevo**
9. **Salud del Programa** — frescura, cobertura, integridad, cuarentena, deriva.
10. **Benchmark Nacional** — series oficiales ROS/ROE de la UAF como denominador público.
11. **Calibración de Reglas** — tasa de no corroboración por regla, reglas mudas.

### Grupo D — Fiscalización y búsqueda
12. **Perímetro UAF** · 13. **Sanciones** · 14. **Perfil por RUT**

## 5. Personas

| Perfil | Entra en | Ve además | No ve |
|---|---|---|---|
| Explorador | Motor de Hallazgos | Territorio, Sectorial, Anomalías | Calibración |
| Investigador | Casos | AML 360°, Red, Evidencia, Perfil | Salud, Benchmark |
| Supervisor | Salud del Programa | Benchmark, Calibración, Casos (agregado) | Perfil individual |
| Data Steward | Evidencia | Salud, cobertura, cuarentena | Casos, hipótesis |

El perfil **filtra y reordena** la navegación; no restringe datos. No es un control de acceso.

## 6. Ciclo de vida del caso

```
DETECTADO ──► EN_REVISION ──► CORROBORADO ──► ESCALADO
     │             │                              │
     └────────► DESCARTADO ◄──────────────────────┘
                    │
                 (motivo tipificado obligatorio)
```

**Motivos de descarte** (`disposition_reason`), catálogo cerrado:

| Código | Significado |
|---|---|
| `EXPLICACION_LEGITIMA` | El patrón tiene explicación económica documentada |
| `ERROR_IDENTIDAD` | La convergencia se apoyaba en identidad mal resuelta |
| `DATO_DESACTUALIZADO` | La fuente cambió y la señal ya no aplica |
| `FUERA_DE_PERIMETRO` | Real, pero fuera del alcance AML (art. 27 Ley 19.913) |
| `EVIDENCIA_INSUFICIENTE` | No corroborable con fuentes disponibles |
| `DUPLICADO` | Ya cubierto por otro caso |

Este catálogo es el insumo directo del módulo **Calibración de Reglas**: una regla cuyo motivo
dominante es `ERROR_IDENTIDAD` tiene un problema de resolución de entidad, no de umbral.

**Guardrail:** ningún estado del caso escribe sobre `signals.jsonl` ni `scores.jsonl`. La
disposición es un objeto del cockpit, no una mutación de la fuente.

## 7. Contrato de datos

`contracts/cockpit_contract_v1.schema.json` define el artefacto único que consume la app.
Secciones: `sources`, `program_health`, `cases`, `anomalies`, `territory`, `sectors`,
`sector_gaps`, `benchmark`, `rules`, `sanctions`, `network`, `guardrails`, `provenance`.

Invariantes exigidos por el esquema:

- Toda señal declara `source_id`, `rule_id`, `period_id` y al menos un `evidence_ref`.
- Todo score declara `score_name`, `score_value`, `score_version`, `score_scope`
  (exigido por los manifiestos de los siete radares).
- `score_scope` sólo admite `INVESTIGATION_PRIORITY`; nunca `ENTITY_RISK`.
- Una fuente sin dato en el período se serializa `"status": "NO_DATA"`, jamás `0`.
- Los códigos territoriales y sectoriales son claves CUT/UAF; los nombres son atributos.

`tools/build_cockpit_data.py` ensambla el artefacto leyendo los `interop/` reales de los
repositorios hermanos, y `tools/uaf_real.py` construye `sectors` y `benchmark` desde el gold de
Radar UAF. `provenance` declara por sección si el origen es `REAL` o `DEMO_SYNTHETIC`, y la
interfaz lo muestra al usuario en cada módulo alimentado por la sobrecapa.

## 8. Stack

Sin dependencias de runtime: HTML + CSS con custom properties + JavaScript ES modules, SVG
generado en el cliente. Se despliega como sitio estático en GitHub Pages, igual que los radares.

Razones: alineación con la operación existente (los radares ya publican Pages sin servidor),
auditabilidad del render, y ausencia de superficie de suministro externa en una herramienta que
maneja análisis de riesgo.

## 9. Roadmap

| Fase | Alcance | Depende de | Estado |
|---|---|---|---|
| **F1** — Contrato y esqueleto | Esquema, catálogo de métricas, app data-driven, fixture | — | **entregada** |
| **F4** — Benchmark y Sectorial reales | Registro UAF, taxonomía y series ROS/ROE oficiales | gold de Radar UAF | **entregada** |
| **F2** — Frescura real por fuente | `fusion_interop_status_v1.json` en la rama de datos de cada radar | 8 repos | pendiente |
| **F3** — Casos persistentes | Estado fuera de memoria | decidir backend | pendiente |
| **F5** — Calibración | Cierre del ciclo disposición → regla | F3 con volumen | pendiente |

**Estado real.** `sources` y `program_health` se derivan de los ocho `interop/` (F1). `sectors` y
`benchmark` se derivan del gold de Radar UAF y de la taxonomía del Context Hub (F4). Las cuatro
métricas que siguen en `NO_DATA` —frescura, disponibilidad, cuarentena y deriva— dependen de F2,
que es trabajo en los repositorios de los radares, no aquí.

### Lo que F4 enseñó sobre el diseño

Construir el benchmark contra datos reales invalidó dos métricas del catálogo propuesto en F1:

- La UAF publica ROS/ROE **sólo como agregados nacionales**, de modo que la intensidad por sector
  no es computable y el módulo se ancló a nivel nacional.
- `entidades_reportantes_total` resultó ser el universo inscrito, no quienes reportaron, lo que
  dejó `KRI_ROS_GAP` fuera de alcance con fuentes públicas.

Ambas se conservan en el catálogo con un campo `availability` que declara la limitación. Es el
comportamiento que el contrato exige: preferir un `NO_DATA` explícito a una aproximación que se
lea como hecho.
