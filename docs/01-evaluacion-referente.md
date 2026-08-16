# Evaluación del referente · AML Cockpit (Dataeconomy)

Evaluación realizada el 2026-08-15 sobre `https://dev.dataeconomy.ai/cockpit/`.

## 0. Nota de método y limitación de acceso

El dominio `dataeconomy.ai` y su entorno `dev.` están **bloqueados por el proxy de egreso** del
entorno de ejecución. No fue posible renderizar la aplicación ni inspeccionar su bundle, sus
endpoints o su DOM.

La evaluación se construyó por triangulación de:

1. **Material público indexado** de las páginas de producto del proveedor (Cockpit, AML Health
   Dashboard, Products, Augmented Analytics) recuperado vía búsqueda.
2. **Convenciones de la categoría**, contrastadas con literatura pública de métricas AML
   (Alessa, Unit21, Bates Group, GCFFC, Quantexa, Flagright).
3. **El prototipo `cockpit.html` v0.6 presente en este repositorio** ("IFL · Intelligence Fusion
   Layer"), que es la línea base propia y el punto de comparación real.

Todo enunciado sobre el referente que no pudo verificarse directamente está marcado como
`[INFERIDO]`. Se aplica aquí el mismo principio que gobierna los radares: **ausencia de dato no
es dato**.

---

## 1. Qué es el AML Cockpit

Es un producto de **operación y supervisión del programa antilavado de una institución
financiera**. No es un radar OSINT ni un motor de descubrimiento sobre datos públicos: asume que
la institución ya tiene un sistema de monitoreo transaccional generando alertas, y se posiciona
**encima** de él.

Su tesis declarada es llevar a las instituciones financieras *"from firm centric to purpose
centric"*: dejar de mirar el cumplimiento como una función interna y mirarlo como un resultado
medible.

### Público objetivo

| Persona | Necesidad que atiende |
|---|---|
| Alert Reviewer / Case Investigator | Cola de trabajo, contexto del cliente, disposición de alertas |
| AML Operations (1ª línea de defensa) | Rendimiento del equipo, productividad, backlog |
| FCC stakeholders / MLRO / BSA Officer | Salud del programa, exposición, defensa ante el supervisor |

---

## 2. Componentes identificados

### 2.1 Alert Reviewer / Case Investigator
Módulo de cola de trabajo. Permite a AML Operations *"look at analyst performance holistically
through KPI & KRI reporting"*. El objeto central no es la entidad: es **el caso**, con ciclo de
vida, responsable, tiempo y desenlace.

### 2.2 Benchmarking contra datos de industria
Capacidad de *"drive actionable insights (trends, risk exposure and suspicious patterns) from
Industry SAR data (FinCEN Stats) by comparing it against a financial institution's SARs"*.

Este es el atributo conceptualmente más fuerte del referente: **la producción propia se mide
contra un denominador público externo**, no contra sí misma. Responde a "¿reporto poco o mucho
para mi sector?", que es exactamente la pregunta que un supervisor hace.

### 2.3 Vista contextual 360° con grafo
*"Establish a contextual view of customer by collating internal and external systems data into
comprehensive AML graph models supporting interactive graph visualization with analytical
capabilities."* Fusión de datos internos y externos en un modelo de grafo navegable.

### 2.4 AML Health Dashboard (producto hermano)
Tableros preconstruidos para *"oversee and monitor the health of AML functions"*. Métricas
típicas de la categoría: volumen de alertas, tasa de falsos positivos, tiempo medio a
disposición, tasa y calidad de SAR, calibración de escenarios.

### 2.5 Metodología de implantación
Assessment de stakeholders → mapeo de soluciones a necesidades → evaluación de *readiness*
(**Data, People, Process**) → priorización por impacto y madurez → roadmap con plan de proyecto.

---

## 3. Fuentes externas que considera

| Fuente | Naturaleza | Uso |
|---|---|---|
| FinCEN SAR Stats | Pública, agregada, sectorial | Denominador de benchmark |
| Sistemas internos (TM, KYC, core) | Privada | Alertas, clientes, transacciones |
| *"External systems data"* | Mixta `[INFERIDO]` | Enriquecimiento del grafo (listas, registros, adverse media) |

**Hallazgo estructural:** el referente consume **una** fuente pública de referencia y muchas
fuentes privadas. Nuestro ecosistema es el espejo exacto: **siete fuentes públicas** y ninguna
privada. Esto no es una debilidad; cambia dónde está el valor. Ver §6.

---

## 4. Métricas que genera

Reconstrucción por categoría. Marcadas `[INFERIDO]` las no verificadas textualmente.

### KPI de operación
- Volumen de alertas por período y por cola `[INFERIDO]`
- Tasa de falsos positivos `[INFERIDO]`
- Tiempo medio a disposición (MTTD) `[INFERIDO]`
- Productividad por analista, casos cerrados por período `[INFERIDO]`
- Backlog y antigüedad de la cola `[INFERIDO]`

### KRI de riesgo
- Exposición de riesgo por segmento/geografía `[INFERIDO]`
- Patrones sospechosos y tendencias
- Concentración de tipologías

### Métricas de calidad regulatoria
- Tasa de emisión de SAR y calidad del SAR `[INFERIDO]`
- Comparación de la tasa propia contra la industria (FinCEN)

### Métricas de modelo
- Umbrales de escenario, calibración, cadencia de reentrenamiento `[INFERIDO]`

---

## 5. Enfoque analítico

| Dimensión | Referente | IFL (línea base v0.6) |
|---|---|---|
| Objeto central | El **caso** y el **analista** | La **entidad** y la **señal** |
| Origen del dato | Interno privado + 1 benchmark público | 7 fuentes públicas OSINT |
| Pregunta que responde | ¿Funciona bien mi programa? | ¿Qué debería mirar primero? |
| Unidad de mérito | Eficiencia operativa | Convergencia de evidencia |
| Ciclo de vida | Alerta → investigación → SAR → cierre | Señal → hallazgo → hipótesis |
| Trazabilidad | Auditoría de caso `[INFERIDO]` | Evidencia y linaje por señal |
| Garantías semánticas | No declaradas públicamente | Guardrails explícitos en UI |

---

## 6. Diagnóstico: qué tomar, qué no, y qué ya tenemos mejor

### Atributos a incorporar (brechas reales de la línea base v0.6)

**A. Ciclo de vida del caso.** El prototipo actual muestra una "cola de prioridad analítica" que
no es una cola: no tiene estado, responsable, antigüedad, SLA ni desenlace. Una tarjeta de
hallazgo no puede cerrarse, escalarse ni descartarse. Sin desenlace registrado no hay
aprendizaje: es imposible saber qué reglas producen ruido.

**B. Salud del programa como primera clase.** El referente mide su propia maquinaria. La v0.6
mide el mundo observado pero no se mide a sí misma: no expone frescura por fuente, cobertura de
identidad canónica, integridad de evidencia ni lotes en cuarentena. Estos datos **ya existen**
en los `interop/integration_manifest_v1.json` y en los `fusion_interop_status_v1.json` de cada
radar, y hoy no llegan a ninguna pantalla.

**C. Benchmark contra denominador público.** El equivalente chileno del FinCEN SAR Stats existe:
las **series estadísticas ROS/ROE publicadas por la UAF** (ya recolectadas por Radar UAF vía
CKAN de `datos.gob.cl`). Permite preguntar "¿este sector produce señales por encima o por debajo
de lo que su masa y su reportabilidad publicada harían esperar?".

**D. Personas.** La v0.6 tiene un solo modo de uso. Un explorador, un investigador de caso y un
supervisor necesitan pantallas de entrada distintas sobre los mismos datos.

**E. Disposición con motivo tipificado.** Cerrar un caso obliga a declarar por qué. Es el insumo
que convierte la operación en calibración de reglas.

### Atributos a NO copiar

- **SAR/ROS como salida.** No somos sujeto obligado. El producto terminal es un **dossier de
  priorización con evidencia**, no un reporte de operación sospechosa. Confundirlos sería un
  error jurídico, no estético.
- **Score de riesgo único y global.** Los manifiestos de los siete radares declaran
  `common_risk_score: false` y `policy: RADAR_SPECIFIC_ONLY`. Un score compuesto sólo es
  admisible como **prioridad de revisión** con contribución desagregada y trazable, nunca como
  medida de riesgo de la entidad.
- **Métricas de productividad individual.** En una institución miden desempeño laboral. Aquí
  sesgarían hacia cerrar casos rápido. Se miden **reglas y fuentes**, no personas.
- **Propagación de riesgo por el grafo.** Ningún vínculo hereda riesgo. Es guardrail duro.

### Dónde la línea base ya es superior

1. **Guardrails semánticos en la interfaz.** La distinción Hecho ≠ Anomalía ≠ Señal AML ≠
   Hipótesis, impresa junto al dato, es un activo que el referente no exhibe públicamente.
2. **Evidence-first con `missing ≠ zero`.** Ya es un principio de arquitectura de los radares.
3. **Multiplicidad de fuentes independientes.** Siete fuentes públicas heterogéneas producen
   convergencia genuina; el referente depende de sistemas de un mismo dueño.
4. **Identidad conformada.** `ENT-RUT-{RUT}` con dígito verificador validado, y política
   explícita `ENTITY_ID_NULL_CANDIDATE_ONLY` para lo no resuelto.

---

## 7. ¿Podemos emular su estética y su potencial?

**Estética: sí, y de hecho ya está alcanzada o superada.** La línea base v0.6 ya implementa un
sistema de tokens con tema claro/oscuro, gráficos SVG sin dependencias externas, tipografía
tabular para cifras y una paleta con color propio por fuente. No requiere ninguna librería ni
activo del referente.

**Potencial: sí, y en un rango más amplio.** El referente está limitado a los datos de su
cliente. Este ecosistema opera sobre el registro público de un país completo, con linaje
verificable. Es un producto distinto y de mayor alcance en cobertura, a cambio de menor
granularidad transaccional.

**Sobre "emular".** No hay objeción. Adoptar conceptos de producto —una cola con ciclo de vida,
métricas de salud del programa, benchmark contra un denominador público— y construir una
identidad visual en la misma familia estética es práctica normal y legítima. La línea que sí se
respeta es no reutilizar activos protegidos del proveedor: su marca, sus textos, su código o sus
capturas. Nada de la propuesta los necesita: la implementación es original y, además, el dominio
estuvo inaccesible, de modo que no hubo material del que copiar aunque se hubiese querido.

---

## 8. Conclusión

El referente aporta **tres ideas de producto que valen la pena** y que hoy faltan: caso con
ciclo de vida, salud del programa medida, y benchmark contra denominador público externo. Aporta
además una **cuarta idea de encuadre**: hablarle a personas distintas con pantallas distintas.

Lo que no aporta —y donde la propuesta debe divergir deliberadamente— es el modelo semántico. La
disciplina de guardrails de los radares es el diferenciador, y debe sobrevivir intacta a la
incorporación de todo lo anterior.

La propuesta concreta está en [`02-arquitectura.md`](02-arquitectura.md) y el catálogo de
métricas en [`03-catalogo-metricas.md`](03-catalogo-metricas.md).

## Fuentes consultadas

- [Cockpit — Dataeconomy](https://dataeconomy.ai/cockpit/)
- [AML Health Dashboard — Dataeconomy](https://dataeconomy.ai/products/aml-health-dashboard/)
- [Products — Dataeconomy](https://dataeconomy.ai/products/)
- [Augmented Analytics — Dataeconomy](https://dataeconomy.ai/capabilities-ai/augmented-analytics/)
- [Key KPIs and Metrics to Monitor in AML and Compliance — Alessa](https://alessa.com/blog/key-kpis-for-aml-compliance/)
- [Is Your AML Case Management System Working? Metrics + AML KPIs — Unit21](https://www.unit21.ai/blog/aml-case-management-system-metrics-and-kpis)
- [A Strategic Guide to AML KPIs and KRIs — Bates Group](https://www.batesgroup.com/news/aml-kpis-and-kris-for-fintechs)
- [Country AML Dashboard Template Including KPI and KRI Data — GCFFC](https://www.gcffc.org/sectors/country-aml-dashboard-template-including-kpi-and-kri-data)
- [Understanding AML Investigations & Case Management — Quantexa](https://www.quantexa.com/resources/aml-investigations-and-case-management/)
