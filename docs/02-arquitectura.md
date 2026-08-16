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
| Módulos | 10 | 13 (+ Salud, + Casos, + Benchmark) |
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
3. **Actividad Sectorial** — 55 actividades UAF, crosswalk UAF↔ACTECO, brechas de reportabilidad.
4. **Anomalías** — patrones contextuales que aún **no** son señal AML gobernada.

### Grupo B — Investigación *(qué hacer con lo que miro)* — **nuevo**
5. **Casos** — cola con estado, antigüedad, SLA, responsable, disposición tipificada.
6. **AML 360°** — vista integrada por entidad.
7. **Red de Relaciones** — vínculos observados, sin herencia de riesgo.
8. **Evidencia** — matriz de cobertura, claves conformadas, linaje.

### Grupo C — Supervisión *(cómo funciona el sistema)* — **nuevo**
9. **Salud del Programa** — frescura, cobertura, integridad, cuarentena, deriva.
10. **Benchmark Sectorial** — producción propia vs. denominador público UAF.
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
`benchmark`, `rules`, `sanctions`, `network`, `guardrails`.

Invariantes exigidos por el esquema:

- Toda señal declara `source_id`, `rule_id`, `period_id` y al menos un `evidence_ref`.
- Todo score declara `score_name`, `score_value`, `score_version`, `score_scope`
  (exigido por los manifiestos de los siete radares).
- `score_scope` sólo admite `INVESTIGATION_PRIORITY`; nunca `ENTITY_RISK`.
- Una fuente sin dato en el período se serializa `"status": "NO_DATA"`, jamás `0`.
- Los códigos territoriales y sectoriales son claves CUT/UAF; los nombres son atributos.

`tools/build_cockpit_data.py` ensambla el artefacto leyendo los `interop/` reales de los
repositorios hermanos.

## 8. Stack

Sin dependencias de runtime: HTML + CSS con custom properties + JavaScript ES modules, SVG
generado en el cliente. Se despliega como sitio estático en GitHub Pages, igual que los radares.

Razones: alineación con la operación existente (los radares ya publican Pages sin servidor),
auditabilidad del render, y ausencia de superficie de suministro externa en una herramienta que
maneja análisis de riesgo.

## 9. Roadmap

| Fase | Alcance | Depende de |
|---|---|---|
| **F1** — Contrato y esqueleto | Esquema, catálogo de métricas, app data-driven, fixture | nada (entregado) |
| **F2** — Salud real | `build_cockpit_data.py` contra los 7 `interop/` reales | acceso a los repos |
| **F3** — Casos persistentes | Estado en repositorio, no en memoria | decidir backend de estado |
| **F4** — Benchmark | Series ROS/ROE UAF desde `datos.gob.cl` | export CKAN en Radar UAF |
| **F5** — Calibración | Cierre del ciclo disposición → regla | F3 con volumen suficiente |

La F1 está implementada en este repositorio. F2 requiere que los radares publiquen
`fusion_interop_status_v1.json` en sus ramas de datos, que ya está declarado en sus manifiestos.
