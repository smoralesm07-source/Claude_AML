# IFL Cockpit · Propuesta v1

Evaluación del **AML Cockpit de Dataeconomy** y propuesta de cockpit analítico para el ecosistema
de radares OSINT con enfoque AML/LA-FT.

```
┌── Evaluación del referente ──────────────────────────────────────────────┐
│  docs/01-evaluacion-referente.md   qué es, qué métricas produce,         │
│                                    qué tomar y qué no                    │
├── Propuesta ────────────────────────────────────────────────────────────┤
│  docs/02-arquitectura.md           módulos, personas, ciclo de caso      │
│  docs/03-catalogo-metricas.md      23 métricas con fórmula y guardrail   │
├── Contratos ───────────────────────────────────────────────────────────-┤
│  contracts/cockpit_contract_v1.schema.json   artefacto que consume la app│
│  contracts/metrics_catalog_v1.json           catálogo legible por máquina│
├── Implementación ──────────────────────────────────────────────────────-┤
│  app/                              cockpit v1, 14 módulos, sin dependencias│
│  tools/build_cockpit_data.py       ensambla el contrato desde los interop│
└──────────────────────────────────────────────────────────────────────────┘
```

## Puesta en marcha

```bash
python3 tools/build_cockpit_data.py --validate   # lee los interop de los radares hermanos
python3 -m http.server 8000                      # desde la raíz del repositorio
# abrir http://localhost:8000/app/
```

El constructor busca los repositorios de los radares en el directorio padre. Para otra ubicación:
`--repos-root /ruta/a/los/repos`. La validación del esquema requiere `pip install jsonschema`.

La aplicación consume el contrato por `fetch`, de modo que abrirla con `file://` no funciona: el
navegador bloquea la petición. La app lo detecta y muestra la instrucción correcta.

## Qué se tomó del referente

El AML Cockpit de Dataeconomy es un producto de **operación y supervisión del programa antilavado
de una institución financiera**. Opera sobre datos internos privados, con una única fuente pública
de referencia. Nuestro ecosistema es el espejo: siete fuentes públicas y ninguna privada.

Tres ideas de producto valían la pena y faltaban en el prototipo v0.6:

| Atributo del referente | Cómo se incorpora |
|---|---|
| Cola con ciclo de vida y disposición | Módulo **Cola de Casos**: estado, SLA, responsable y motivo de descarte tipificado |
| Salud del programa medida | Módulo **Salud del Programa**: 14 KPI derivados de los `interop/` reales de cada radar |
| Benchmark contra denominador público (FinCEN SAR Stats) | Módulo **Benchmark Sectorial**: señales propias contra series ROS/ROE publicadas por la UAF |
| Personas distintas, pantallas distintas | Selector de perfil que reordena la navegación: Explorador, Investigador, Supervisor, Data Steward |

Se añadió un cuarto módulo que el referente no tiene y que el ciclo de disposición hace posible:
**Calibración de Reglas**, donde el desenlace analítico realimenta la regla que originó la señal.

## Qué se rechazó deliberadamente

- **SAR/ROS como producto terminal.** No somos sujeto obligado. La salida es un dossier de
  priorización con evidencia.
- **Score de riesgo único y global.** Los siete radares declaran `common_risk_score: false`. El
  score del cockpit es `INVESTIGATION_PRIORITY` con contribución desagregada y trazable.
- **Métricas de productividad individual.** Se miden reglas y fuentes, nunca personas.
- **Propagación de riesgo por el grafo.** Ningún vínculo hereda riesgo.

## Sobre emular

No hay objeción de fondo. Adoptar conceptos de producto y construir una identidad visual en la
misma familia estética es práctica normal. La línea que sí se respeta es no reutilizar activos
protegidos del proveedor —marca, textos, código o capturas—, y nada de esta propuesta los necesita:
la implementación es original.

Conviene además dejar constancia de una limitación: el dominio `dataeconomy.ai` está **bloqueado
por el proxy de egreso** de este entorno, de modo que la aplicación no pudo inspeccionarse
directamente. La evaluación se construyó por triangulación de material público indexado y
convenciones de la categoría, y marca `[INFERIDO]` todo lo no verificado. Ver
[`docs/01-evaluacion-referente.md`](docs/01-evaluacion-referente.md) §0.

## Estado de la implementación

**Fase F1 completa.** Los 14 módulos renderizan desde el contrato; ninguna cifra está incrustada en
la interfaz.

Las secciones `sources` y `program_health` se derivan de los
`interop/integration_manifest_v1.json` **reales** de los ocho repositorios del ecosistema. Esto ya
produce hallazgos de operación:

- Cobertura territorial conformada en **66,7%** — SII, CGR, Presupuesto y OSFL siguen en
  `ADAPTER_PARTIAL` para `territory_id`.
- Cobertura sectorial en **70%** — tres fuentes no declaran bloque `sector`.
- Resolución de identidad en **100%** — el Entity Hub `ENT-RUT-{RUT}` está conformado en todas las
  fuentes donde la identidad es dimensión primaria.
- **4 métricas en `NO_DATA`** porque exigen que los radares publiquen
  `fusion_interop_status_v1.json` en su rama de datos. Se muestran como `—`, nunca como `0`.

**Fase F4 adelantada: Benchmark y Sectorial con datos reales.** Las secciones `sectors` y
`benchmark` se construyen desde `Radar_UAF/data/gold/` y la taxonomía del Context Hub:

- **9.782 sujetos obligados inscritos** en 52 actividades del registro UAF
- **97,2%** cruza de forma exacta contra las 55 actividades de la taxonomía; las 12 glosas
  restantes se reportan como brecha y **no se fuerzan** por similitud
- Series oficiales **ROS/ROE 2021–2025** con URL de origen por punto: los ROS crecen **+124,2%**
  mientras el universo inscrito crece 21,8%
- **2 actividades acumulan la mitad del universo**: Usuarios de Zonas Francas (2.840) y Gestión
  Inmobiliaria (2.244)

Construir esto contra datos reales invalidó dos métricas de mi propio catálogo, y ambas quedaron
declaradas como no computables en vez de aproximadas:

- `BMK_SIGNAL_INTENSITY` → `NATIONAL_ONLY`: la UAF no publica ROS/ROE por actividad.
- `KRI_ROS_GAP` → `OUT_OF_SCOPE_PUBLIC_SOURCES`: `entidades_reportantes_total` **no** son quienes
  reportaron; su valor coincide exactamente con el universo inscrito (9.403 + 508 = 9.911 en 2025).
  Derivar de ahí una tasa de cumplimiento habría producido un indicador falso.

El constructor además levanta una bandera de calidad sobre la fuente: la serie
`procesos_sancionatorios_iniciados` registra 0 en 2021 y 2025 entre valores de 51 a 117, publicados
con confianza 1,0. El cockpit no corrige a la fuente; lo marca para verificación.

Las secciones `cases`, `anomalies`, `territory`, `rules`, `sanctions` y `network` siguen viniendo de
`tools/demo_overlay.json`, una **sobrecapa demostrativa con entidades y cifras sintéticas**. El
archivo está marcado `"_synthetic": true`, las entidades no representan personas ni organizaciones
reales, y **la propia interfaz lo declara** con un aviso en cada módulo afectado.

El roadmap por fases está en [`docs/02-arquitectura.md`](docs/02-arquitectura.md) §9.

## Invariantes que la propuesta no negocia

1. Ninguna métrica del cockpit escribe sobre `signals.jsonl` ni `scores.jsonl` de los radares.
2. Ninguna métrica se desagrega por analista individual.
3. Ninguna anomalía de fiscalización se promueve automáticamente a señal AML.
4. Ninguna relación observada propaga riesgo entre sus extremos.
5. Toda ausencia de dato se serializa `NO_DATA` y se renderiza `—`, nunca `0`.
6. Toda señal declara fuente, regla, período y al menos una referencia de evidencia.

## Línea base

`cockpit.html` se conserva sin modificar: es el prototipo **v0.6** con datos incrustados que sirvió
de punto de comparación. La v1 vive en `app/` y no lo reemplaza en disco.
