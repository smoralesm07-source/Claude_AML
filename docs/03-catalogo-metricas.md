# Catálogo de métricas · IFL Cockpit v1

Versión legible de [`contracts/metrics_catalog_v1.json`](../contracts/metrics_catalog_v1.json).
La fuente de verdad es el JSON; este documento explica el razonamiento.

**Regla de gobierno:** ninguna métrica aparece en la interfaz sin estar registrada en el catálogo
con fórmula, fuente de verdad, umbrales y guardrail. La aplicación no calcula métricas nuevas ni
reformatea identificadores: copia `name` y `guardrail` desde el catálogo al contrato.

## Familias

| Familia | Qué mide | Origen conceptual |
|---|---|---|
| `KPI_PROGRAMA` | La maquinaria analítica a sí misma | AML Health Dashboard del referente |
| `KRI_UNIVERSO` | Riesgo o exposición del universo observado | Núcleo propio del ecosistema IFL |
| `BENCHMARK` | Producción propia contra denominador público | Benchmark FinCEN SAR Stats del referente |
| `CALIBRACION` | Desenlace analítico realimentando la regla | Derivado del ciclo de disposición |

---

## KPI_PROGRAMA — salud del programa

Catorce métricas. Es la brecha más grande de la v0.6: el prototipo medía el mundo observado pero
no se medía a sí mismo, pese a que los datos ya existían en los `interop/` de cada radar.

| Métrica | Fórmula | Umbrales | Guardrail esencial |
|---|---|---|---|
| Frescura por fuente | `hoy − último snapshot exitoso` | ≤ SLA / ≤ 2×SLA / > 2×SLA | El SLA es propio de cada fuente: Presupuesto publica diario, UAF anual. Comparar frescura entre cadencias distintas no tiene sentido |
| Disponibilidad de fuente | corridas exitosas / intentadas | ≥95 / ≥80 / <80 | Una caída no se rellena con el último valor conocido |
| Resolución de identidad | registros con `entity_id` válido / con entidad declarada | ≥90 / ≥70 / <70 | El resto no es error: es `ENTITY_ID_NULL_CANDIDATE_ONLY` por política |
| Cobertura territorial | registros con `territory_id` CUT / con territorio declarado | ≥95 / ≥75 / <75 | Nombre de comuna no es clave |
| Cobertura sectorial | entidades con `sector_id` UAF / con ACTECO declarado | ≥80 / ≥60 / <60 | ACTECO no acredita condición de sujeto obligado |
| Integridad de evidencia | señales con `evidence_ref` resoluble / totales | =100 / ≥98 / <98 | Invariante duro: sin evidencia, la señal se cuarentena en vez de mostrarse |
| Lotes en cuarentena | lotes `QUARANTINED` en el período | 0 / ≤2 / >2 | La cuarentena indica que el control funcionó, no que el dato sea falso |
| Backlog de la cola | casos en `DETECTADO` o `EN_REVISION` | ≤25 / ≤60 / >60 | No se lee solo: se lee junto a la antigüedad |
| Antigüedad de la cola | p90 de `hoy − apertura` | ≤15 / ≤45 / >45 | Se usa p90 y no promedio: el promedio oculta las colas largas |
| Tiempo medio a disposición | mediana de `disposición − apertura` | ≤10 / ≤25 / >25 | **Nunca se desagrega por analista** |
| Cumplimiento de SLA | dispuestos en plazo / dispuestos | ≥90 / ≥70 / <70 | El SLA depende del nivel; un agregado sin desglose es engañoso |
| Deriva de volumen | período / mediana de 12 previos − 1 | \|·\|>50 / \|·\|>150 | Una deriva fuerte suele indicar cambio en la publicación de la fuente, no en el fenómeno |
| Convergencia multifuente | entidades con ≥3 fuentes / con ≥1 señal | ≥15 / ≥5 / <5 | Mide capacidad de cruce, no gravedad. Convergencia baja suele ser brecha de identidad |
| Reglas sin producción | reglas activas con 0 señales en 3 períodos | ≤2 / ≤6 / >6 | Una regla muda puede estar bien calibrada o rota. Revisión, no desactivación automática |

### Por qué el tiempo a disposición no se desagrega por persona

En una institución financiera esta métrica evalúa desempeño laboral. Trasladada tal cual a un
equipo analítico pequeño, el incentivo se invierte: premia cerrar casos rápido, que es exactamente
el comportamiento que arruina la calidad del triaje. La métrica se conserva porque diagnostica
reglas que producen trabajo caro; el corte por persona se omite por diseño, no por olvido.

---

## KRI_UNIVERSO — riesgo del universo observado

| Métrica | Grano | Guardrail esencial |
|---|---|---|
| Score de prioridad de revisión | Entidad | **No es riesgo de la entidad.** `score_scope: INVESTIGATION_PRIORITY`, con contribución desagregada y trazable a la señal de origen |
| Exposición territorial compuesta | Territorio | Criminalidad general ≠ riesgo LA/FT. Sólo entran categorías con vínculo preciso al art. 27 de la Ley 19.913. Un territorio expuesto no transfiere riesgo a las entidades domiciliadas en él |
| Brecha de reportabilidad ROS | Sector | No reportar no es infracción por sí solo: puede no haber operaciones sospechosas que reportar |
| Candidatos a perímetro no inscritos | Sector | `MATCH_FUERTE` identifica candidatos a validación, no sujetos obligados |

### El score compuesto y el contrato de los radares

Los ocho manifiestos `interop/integration_manifest_v1.json` declaran:

```json
"scores": { "common_risk_score": false, "policy": "RADAR_SPECIFIC_ONLY" }
```

Un score compuesto entre radares contradice esa declaración si se presenta como riesgo. La salida
es semántica, no técnica: el score existe **sólo en el cockpit**, se llama `ifl_priority_score`,
declara `score_scope: INVESTIGATION_PRIORITY` y expone qué aportó cada fuente. Es orden de
revisión, no medida de riesgo. El esquema del contrato fija `score_scope` como constante para
impedir que se degrade a `ENTITY_RISK` por descuido.

---

## BENCHMARK — contraste contra denominador público

El referente compara los SAR del cliente contra las estadísticas de industria de FinCEN. El
equivalente chileno existe y **ya está implementado con datos reales** desde
`Radar_UAF/data/gold/statistics.parquet`.

### Lo que la fuente sí sostiene

| Métrica | Disponibilidad | Valor real (2025) |
|---|---|---|
| ROS por sujeto obligado inscrito | `REAL` | 2,2 ROS/entidad |
| ROE por sujeto obligado inscrito | `REAL` | 163,5 ROE/entidad |
| Variación de ROS 2021–2025 | `REAL` | +124,2% |
| Equivalencia exacta registro-taxonomía | `REAL` | 97,2% (9.508 de 9.782) |

Series completas 2021–2025 de ROS, ROE, universo inscrito, acciones de supervisión y procesos
sancionatorios, cada punto con su URL de origen.

### Dos métricas que el diseño original daba por hechas y la fuente no sostiene

Al construir el módulo contra datos reales, dos métricas del catálogo resultaron no computables.
Se conservan con su definición correcta y un campo `availability` que lo declara, en vez de
borrarlas o —peor— aproximarlas.

**`BMK_SIGNAL_INTENSITY` → `NATIONAL_ONLY`.** La UAF publica ROS y ROE como **agregados
nacionales**, sin desagregación por actividad supervisada. La intensidad por sector no existe como
dato público. El benchmark se ancla a nivel nacional; la desagregación sectorial se limita al
universo inscrito, que sí es un hecho registral por actividad.

**`KRI_ROS_GAP` → `OUT_OF_SCOPE_PUBLIC_SOURCES`.** La métrica publicada
`entidades_reportantes_total` **no identifica a quienes reportaron**: su valor coincide
exactamente con el universo inscrito.

```
sujetos_obligados_sector_privado  2025 = 9.403
entidades_publicas_registradas    2025 =   508
                                  suma = 9.911
entidades_reportantes_total       2025 = 9.911   ← idéntico
```

Derivar de ahí una «tasa de cumplimiento» habría producido un indicador falso con apariencia de
rigor. Es exactamente el error que el principio `missing ≠ zero` existe para evitar, aplicado un
nivel más arriba: no basta con no inventar ceros, hay que no inventar denominadores.

### Control de calidad sobre la fuente

El constructor marca ceros rodeados de valores distintos de cero dentro de una misma serie.
`procesos_sancionatorios_iniciados` registra 0 en 2021 y 2025 mientras el resto del período va de
51 a 117, y el radar los publica como hecho oficial con confianza 1,0. El cockpit **no corrige a la
fuente**: levanta la bandera para que el Data Steward la verifique contra el informe original.

---

## CALIBRACION — el desenlace realimenta la regla

Esta familia sólo es posible porque el ciclo de vida del caso obliga a declarar un motivo al
descartar. Es el retorno de haber incorporado la cola con disposición.

| Métrica | Guardrail esencial |
|---|---|
| Tasa de no corroboración por regla | Equivalente funcional del *false positive rate*, con nombre distinto a propósito: una señal no corroborada no era falsa, era insuficiente. Requiere ≥20 disposiciones |
| Mezcla de motivos de descarte | Diagnóstico, no puntaje |
| Contribución de regla a escalados | Contribución no es causalidad |

### La mezcla de motivos es el diagnóstico

Dos reglas con la misma tasa de no corroboración pueden necesitar remedios opuestos:

| Motivo dominante | Qué significa | Remedio |
|---|---|---|
| `ERROR_IDENTIDAD` | La convergencia se apoyaba en identidad mal resuelta | Arreglar la resolución de entidad, no el umbral |
| `EXPLICACION_LEGITIMA` | El patrón tiene explicación económica documentada | Ajustar el umbral o añadir un filtro de contexto |
| `DATO_DESACTUALIZADO` | La fuente cambió y la señal ya no aplica | Revisar frescura y cadencia de esa fuente |
| `FUERA_DE_PERIMETRO` | Real, pero fuera del art. 27 de la Ley 19.913 | Reclasificar la regla como fiscalización, no AML |

En la sobrecapa demostrativa, `SAN.R09_MATCH_POR_NOMBRE` tiene 89,4% de no corroboración con
`ERROR_IDENTIDAD` dominante: no es una regla mal calibrada, es una regla que opera sobre
resoluciones sancionatorias que no traen RUT. Bajarle el umbral no arreglaría nada.

---

## Invariantes duros

Declarados en `hard_invariants` del catálogo y verificados por el esquema del contrato:

1. Ninguna métrica escribe sobre `signals.jsonl` ni `scores.jsonl` de los radares.
2. Ninguna métrica se desagrega por analista individual.
3. Ninguna anomalía de fiscalización se promueve automáticamente a señal AML.
4. Ninguna relación observada propaga riesgo entre sus extremos.
5. Toda ausencia de dato se serializa `NO_DATA` y se renderiza `—`, nunca `0`.
6. Todo score expuesto declara `score_name`, `score_value`, `score_version` y `score_scope`.
