/* IFL Cockpit v1 — aplicación.
   No contiene reglas de negocio AML: proyecta el contrato producido por la capa
   de fusión y registra qué hizo el analista. Si una cifra aparece aquí, existe un
   archivo de un radar que la respalda. */

import {
  fmt, level, levelLabel, levelVar, gauge, sparkline, donut, hbar, vbar,
  linechart, chileMap, networkGraph,
} from './charts.js';

const CONTRACT_URL = new URL('../data/cockpit_contract_v1.json', import.meta.url);

/* ── Catálogo de fuentes: etiqueta y token de color ─────────── */
const SRC = {
  sii: 'SII', uaf: 'UAF', cgr: 'CGR', del: 'Delictual',
  pre: 'Presupuesto', san: 'Sanciones', osl: 'OSFL', ctx: 'Context Hub',
};
const srcLabel = (id) => SRC[id] || id;
const badge = (id) => `<span class="bd ${id}">${srcLabel(id)}</span>`;

const STATE_LABEL = {
  DETECTADO: 'Detectado', EN_REVISION: 'En revisión', CORROBORADO: 'Corroborado',
  ESCALADO: 'Escalado', DESCARTADO: 'Descartado',
};
const REASON_LABEL = {
  EXPLICACION_LEGITIMA: 'Explicación legítima', ERROR_IDENTIDAD: 'Error de identidad',
  DATO_DESACTUALIZADO: 'Dato desactualizado', FUERA_DE_PERIMETRO: 'Fuera de perímetro',
  EVIDENCIA_INSUFICIENTE: 'Evidencia insuficiente', DUPLICADO: 'Duplicado',
};
const OPEN_STATES = ['DETECTADO', 'EN_REVISION', 'CORROBORADO'];

/* ── Módulos y personas ─────────────────────────────────────── */
const MODULES = {
  hallazgos:   { t: 'Motor de Hallazgos',    ic: '🎯', g: 'Exploración' },
  territorio:  { t: 'Análisis Territorial',  ic: '🗺',  g: 'Exploración' },
  sectorial:   { t: 'Actividad Sectorial',   ic: '📊', g: 'Exploración' },
  anomalias:   { t: 'Anomalías',             ic: '⚠️', g: 'Exploración' },
  casos:       { t: 'Cola de Casos',         ic: '🗂',  g: 'Investigación' },
  aml360:      { t: 'AML 360°',              ic: '🔎', g: 'Investigación' },
  red:         { t: 'Red de Relaciones',     ic: '🔗', g: 'Investigación' },
  evidencia:   { t: 'Evidencia',             ic: '📋', g: 'Investigación' },
  salud:       { t: 'Salud del Programa',    ic: '💓', g: 'Supervisión' },
  benchmark:   { t: 'Benchmark Nacional',    ic: '⚖️', g: 'Supervisión' },
  calibracion: { t: 'Calibración de Reglas', ic: '🎚', g: 'Supervisión' },
  fiscal:      { t: 'Perímetro UAF',         ic: '🏛',  g: 'Fiscalización' },
  sanciones:   { t: 'Sanciones',             ic: '⚖️', g: 'Fiscalización' },
  perfil:      { t: 'Perfil por RUT',        ic: '🔍', g: 'Búsqueda' },
};

/* El perfil reordena y filtra la navegación. No es control de acceso: es
   encuadre. Cada perfil entra por el módulo que responde su pregunta. */
const PERSONAS = {
  EXPLORADOR:   { label: 'Explorador',    home: 'hallazgos',
                  mods: ['hallazgos', 'territorio', 'sectorial', 'anomalias', 'casos', 'aml360', 'evidencia', 'perfil'] },
  INVESTIGADOR: { label: 'Investigador',  home: 'casos',
                  mods: ['casos', 'aml360', 'red', 'evidencia', 'perfil', 'hallazgos', 'anomalias', 'sanciones'] },
  SUPERVISOR:   { label: 'Supervisor',    home: 'salud',
                  mods: ['salud', 'benchmark', 'calibracion', 'casos', 'territorio', 'sectorial', 'fiscal', 'sanciones'] },
  STEWARD:      { label: 'Data Steward',  home: 'evidencia',
                  mods: ['evidencia', 'salud', 'calibracion', 'sectorial', 'territorio'] },
};

/* ── Estado de la aplicación ────────────────────────────────── */
const app = {
  data: null,
  persona: 'EXPLORADOR',
  module: 'hallazgos',
  region: 'CL-REG-13',
  mapLayer: 'exposure',
  entityFilter: null,
};

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

/* ── Helpers de presentación ────────────────────────────────── */

/** Renderiza los guardrails cuyo `scope` cubre el módulo actual. */
function guardrails(moduleId) {
  return (app.data.guardrails || [])
    .filter((g) => g.scope.includes('*') || g.scope.includes(moduleId))
    .map((g) => `<div class="gr"><strong>${esc(g.title)}:</strong> ${esc(g.text)}</div>`)
    .join('');
}

/* Qué sección del contrato alimenta cada módulo, para declarar su procedencia. */
const MODULE_SECTION = {
  hallazgos: 'cases', casos: 'cases', aml360: 'cases', perfil: 'cases',
  red: 'network', anomalias: 'anomalies', territorio: 'territory',
  sectorial: 'sectors', fiscal: 'sectors', benchmark: 'benchmark',
  calibracion: 'rules', sanciones: 'sanctions',
};

/** Declara en pantalla si el módulo se alimenta de datos reales o de la demo. */
function provenanceBanner(moduleId) {
  const section = MODULE_SECTION[moduleId];
  const origin = (app.data.provenance || {})[section];
  if (!section || origin === 'REAL') return '';
  if (!origin) return '';
  return `<div class="banner demo"><strong>Datos demostrativos.</strong>
    La sección <code class="mono">${section}</code> proviene de
    <code class="mono">tools/demo_overlay.json</code>: entidades, RUT y cifras
    <strong>sintéticos</strong>, para ejercitar el módulo hasta que la capa de fusión la
    materialice. No representan personas ni organizaciones reales.</div>`;
}

/** Valor de una métrica del catálogo. `null` se muestra '—', nunca 0. */
function metric(metricId, scope = 'GLOBAL') {
  return (app.data.program_health || []).find(
    (m) => m.metric_id === metricId && m.scope === scope);
}

function metricValue(metricId, scope = 'GLOBAL') {
  const m = metric(metricId, scope);
  if (!m || m.value === null) return '—';
  return `${fmt(m.value)}${m.unit === '%' ? '%' : ''}`;
}

function kpi(label, value, sub, cls = 'acc', spark = '', tip = '') {
  const nodata = value === '—';
  return `<div class="kpi ${nodata ? 'nodata' : cls}"${tip ? ` title="${esc(tip)}"` : ''}>
    <div class="kl">${esc(label)}</div>
    <div class="kv ${nodata ? 'nodata' : ''}">${value}</div>
    <div class="ks">${esc(sub)}</div>
    ${spark ? `<div class="ksp">${spark}</div>` : ''}
  </div>`;
}

const statusClass = { OK: 'ok', WARN: 'warn', CRIT: 'crit', NO_DATA: 'nodata' };
const statusRk = { OK: 'lo', WARN: 'hi', CRIT: 'cr', NO_DATA: 'nd' };

function signalChip(sig) {
  return `<span class="sc" style="background:var(--${sig.source_id}-bg);color:var(--${sig.source_id}-tx);border-color:var(--${sig.source_id})">
    ${srcLabel(sig.source_id)}: ${esc(sig.text)} <span class="rid">${esc(sig.rule_id)}</span></span>`;
}

function caseCard(c) {
  const cls = level(c.score.score_value);
  const sources = [...new Set(c.signals.map((s) => s.source_id))];
  const disp = c.disposition_reason
    ? `<span class="rk lo">${REASON_LABEL[c.disposition_reason]}</span>` : '';
  return `<div class="hcard ${cls}">
    <div class="htop">
      <div class="hid">
        <h3>${esc(c.name)}</h3>
        <div class="rut">${c.rut ? `RUT ${esc(c.rut)}` : 'Identidad no resuelta'} · ${esc(c.entity_type)} · ${esc(c.region_label)}</div>
        <div class="metas">
          <span class="st ${c.state}">${STATE_LABEL[c.state]}</span>
          ${disp}
          ${sources.map(badge).join('')}
        </div>
      </div>
      <div class="hscore">${gauge(c.score.score_value)}
        <div style="margin-top:4px"><span class="rk ${cls}">${levelLabel(c.score.score_value)}</span></div>
      </div>
    </div>
    <div class="sigs">${c.signals.map(signalChip).join('')}</div>
    <div class="hyp"><div class="hyp-lbl">Hipótesis analítica</div>
      <div class="hyp-tx">${esc(c.hypothesis)}</div></div>
    ${c.next_steps?.length
      ? `<div class="nxt">${c.next_steps.map((s) => `<span class="nxt-s">→ ${esc(s)}</span>`).join('')}</div>`
      : ''}
  </div>`;
}

const contentWidth = () => Math.max(320, ($('ct')?.offsetWidth || 900) - 44);

/* ── Módulos ────────────────────────────────────────────────── */

function rHallazgos() {
  const open = app.data.cases.filter((c) => OPEN_STATES.includes(c.state));
  const sorted = [...open].sort((a, b) => b.score.score_value - a.score.score_value);
  const allSignals = app.data.cases.flatMap((c) => c.signals);
  const critical = open.filter((c) => c.score.score_value >= 80).length;
  const series = app.data.signal_series;
  const W = contentWidth();

  const bySource = Object.entries(
    allSignals.reduce((acc, s) => ({ ...acc, [s.source_id]: (acc[s.source_id] || 0) + 1 }), {}))
    .map(([id, v]) => ({ l: srcLabel(id), v, c: `var(--${id})` }));

  return `
    <div class="mh"><h1>Motor de Hallazgos</h1>
      <p>Entidades con mayor convergencia de señales independientes · Ordenadas por prioridad de revisión · ${app.data.sources.length} fuentes</p></div>
    ${guardrails('hallazgos')}
    <div class="krow">
      ${kpi('Casos abiertos', fmt(open.length), `${critical} en nivel crítico`, 'cr')}
      ${kpi('Señales activas', fmt(allSignals.length), `De ${new Set(allSignals.map((s) => s.source_id)).size} fuentes independientes`, 'pre')}
      ${kpi('Convergencia multifuente', metricValue('PRG_SOURCE_CONVERGENCE'), 'Casos con ≥3 fuentes', 'uaf')}
      ${kpi('Integridad de evidencia', metricValue('PRG_EVIDENCE_INTEGRITY'), 'Señales con evidencia trazable', 'sii')}
      ${kpi('Anomalías detectadas', fmt(app.data.anomalies.length), `${app.data.anomalies.filter((a) => !a.corroborated).length} sin corroborar`, 'san')}
      ${kpi('Cobertura territorial', `${app.data.territory.length}/16`, 'Regiones con datos activos', 'acc')}
    </div>
    <div class="g2">
      <div class="card"><div class="ct">Evolución de señales · ${esc(app.data.period_id)}</div>
        ${linechart(series.series.map((s) => ({ data: s.data, c: `var(--${s.source_id})` })), series.labels, W / 2 - 40, 120)}
        <div style="display:flex;gap:14px;margin-top:8px;font-size:11px;flex-wrap:wrap">
          ${series.series.map((s) => `<span style="color:var(--${s.source_id})">■ ${esc(s.label)}</span>`).join('')}
        </div>
      </div>
      <div class="card" style="display:flex;flex-direction:column;align-items:center">
        <div class="ct" style="width:100%">Señales por fuente</div>
        ${donut(bySource, 170, 170, 'señales')}
      </div>
    </div>
    <div style="font-size:13px;font-weight:700;margin-bottom:12px;letter-spacing:-.02em">Cola de prioridad analítica</div>
    ${sorted.map(caseCard).join('')}`;
}

function rCasos() {
  const cases = app.data.cases;
  const open = cases.filter((c) => OPEN_STATES.includes(c.state));
  const closed = cases.filter((c) => c.disposed_at);
  const byState = Object.fromEntries(
    Object.keys(STATE_LABEL).map((s) => [s, cases.filter((c) => c.state === s).length]));

  const rows = [...cases]
    .sort((a, b) => b.score.score_value - a.score.score_value)
    .map((c) => `<tr>
      <td><strong>${esc(c.name)}</strong><br><code class="rut">${c.rut ? esc(c.rut) : 'identidad no resuelta'}</code></td>
      <td><span class="st ${c.state}">${STATE_LABEL[c.state]}</span></td>
      <td class="num"><span class="rk ${level(c.score.score_value)}">${c.score.score_value}</span></td>
      <td class="num">${esc(c.opened_at)}</td>
      <td class="num">${c.sla_due_at ? esc(c.sla_due_at) : '<span class="nodata-cell">—</span>'}</td>
      <td>${c.assignee_role ? esc(PERSONAS[c.assignee_role]?.label || c.assignee_role) : '<span class="nodata-cell">sin asignar</span>'}</td>
      <td>${c.disposition_reason ? esc(REASON_LABEL[c.disposition_reason]) : '<span class="nodata-cell">—</span>'}</td>
      <td class="num">${c.signals.length}</td>
    </tr>`).join('');

  const stateSegs = Object.entries(byState)
    .filter(([, v]) => v > 0)
    .map(([k, v]) => ({
      l: STATE_LABEL[k], v,
      c: { DETECTADO: 'var(--nd)', EN_REVISION: 'var(--cgr)', CORROBORADO: 'var(--ch)',
           ESCALADO: 'var(--cr)', DESCARTADO: 'var(--cl)' }[k],
    }));

  return `
    <div class="mh"><h1>Cola de Casos</h1>
      <p>Ciclo de vida analítico · Estado, antigüedad, SLA y disposición tipificada</p></div>
    ${guardrails('casos')}
    <div class="gr"><strong>Invariante:</strong> el estado del caso es un objeto del cockpit.
      Ningún cambio de estado escribe sobre <code class="mono">signals.jsonl</code> ni
      <code class="mono">scores.jsonl</code> de los radares.</div>
    <div class="krow">
      ${kpi('Backlog abierto', metricValue('PRG_QUEUE_BACKLOG'), `${byState.DETECTADO} sin asignar`, 'cr')}
      ${kpi('Antigüedad p90', metricValue('PRG_QUEUE_AGING'), 'Percentil 90 de casos abiertos', 'warn')}
      ${kpi('Tiempo a disposición', metricValue('PRG_MTTD'), 'Mediana de casos cerrados', 'pre')}
      ${kpi('Cumplimiento de SLA', metricValue('PRG_SLA_COMPLIANCE'), `${closed.length} casos dispuestos`, 'ok')}
      ${kpi('Escalados', fmt(byState.ESCALADO), 'Con convergencia sostenida', 'san')}
    </div>
    <div class="g21">
      <div class="card"><div class="ct">Cola completa</div>
        <div class="scroll-x"><table class="dtbl">
          <thead><tr><th>Entidad</th><th>Estado</th><th class="num">Prioridad</th><th class="num">Apertura</th>
          <th class="num">SLA</th><th>Responsable</th><th>Disposición</th><th class="num">Señales</th></tr></thead>
          <tbody>${rows}</tbody></table></div>
      </div>
      <div class="card" style="display:flex;flex-direction:column;align-items:center">
        <div class="ct" style="width:100%">Distribución por estado</div>
        ${donut(stateSegs, 160, 160, 'casos')}
      </div>
    </div>
    <div style="font-size:13px;font-weight:700;margin:4px 0 12px;letter-spacing:-.02em">Casos abiertos</div>
    ${open.sort((a, b) => b.score.score_value - a.score.score_value).map(caseCard).join('')}`;
}

function rSalud() {
  const sources = app.data.sources;
  const keyLabel = { NATIVE: 'Nativo', READY: 'Listo', PARTIAL: 'Parcial', NOT_PRIMARY: 'No aplica' };
  const keyMark = (v) => {
    if (v === null || v === undefined) return '<span class="nodata-cell">—</span>';
    const color = { NATIVE: 'var(--cl)', READY: 'var(--cl)', PARTIAL: 'var(--cm)', NOT_PRIMARY: 'var(--nd)' }[v];
    return `<span style="color:${color};font-weight:600;font-size:11px">${keyLabel[v]}</span>`;
  };

  const srcRows = sources.map((s) => `<tr>
    <td><strong>${esc(s.label)}</strong><br><code class="rut">${esc(s.repository)}</code></td>
    <td><span class="rk ${statusRk[s.status]}">${s.status}</span></td>
    <td><code class="mono" style="font-size:10px">${esc(s.implementation_stage)}</code></td>
    <td>${keyMark(s.conformed_keys.entity_id)}</td>
    <td>${keyMark(s.conformed_keys.territory_id)}</td>
    <td>${keyMark(s.conformed_keys.sector_id)}</td>
    <td>${keyMark(s.conformed_keys.period_id)}</td>
    <td>${esc(s.update_cadence)}</td>
    <td class="num">${s.freshness_days === null ? '<span class="nodata-cell">—</span>' : fmt(s.freshness_days)}</td>
  </tr>`).join('');

  const globals = app.data.program_health.filter((m) => m.scope === 'GLOBAL');
  const cards = globals.map((m) => {
    const val = m.value === null ? '—' : `${fmt(m.value)}${m.unit === '%' ? '%' : ''}`;
    const target = m.target !== null && m.target !== undefined
      ? `Objetivo ${fmt(m.target)}${m.unit === '%' ? '%' : ` ${m.unit}`}` : m.unit;
    return kpi(m.name || m.metric_id, val, target, statusClass[m.status], '', m.guardrail || '');
  }).join('');

  const noData = globals.filter((m) => m.status === 'NO_DATA');

  return `
    <div class="mh"><h1>Salud del Programa</h1>
      <p>La maquinaria analítica medida a sí misma · Derivado de los manifiestos interop reales de cada radar</p></div>
    ${guardrails('salud')}
    <div class="krow">${cards}</div>
    ${noData.length ? `<div class="banner demo"><strong>${noData.length} métricas en NO_DATA.</strong>
      Requieren que los radares publiquen <code class="mono">fusion_interop_status_v1.json</code> en su rama de datos
      (fase F2 del roadmap). Se muestran como '—' y nunca como 0.</div>` : ''}
    <div class="card"><div class="ct">Estado de fuentes y claves conformadas</div>
      <div class="scroll-x"><table class="dtbl">
        <thead><tr><th>Fuente</th><th>Estado</th><th>Etapa interop</th>
          <th>entity_id</th><th>territory_id</th><th>sector_id</th><th>period_id</th>
          <th>Cadencia</th><th class="num">Frescura</th></tr></thead>
        <tbody>${srcRows}</tbody></table></div>
      <div style="margin-top:12px;font-size:11px;color:var(--txm)">
        Las columnas de clave se derivan del <code class="mono">current_status</code> declarado en
        <code class="mono">interop/integration_manifest_v1.json</code> de cada repositorio.
        «No aplica» significa que la dimensión no es primaria para esa fuente: no cuenta ni a favor ni en contra de la cobertura.
      </div>
    </div>`;
}

function rBenchmark() {
  const b = app.data.benchmark;
  const W = contentWidth();
  const cov = b.coverage || {};
  const ser = (m) => b.series.find((s) => s.metric === m);
  const last = (m) => { const s = ser(m); return s ? s.points[s.points.length - 1] : null; };

  const labels = (ser('ros_recibidos')?.points || []).map((p) => p.period);
  const lines = [
    { m: 'ros_recibidos', c: 'var(--uaf)' },
    { m: 'entidades_reportantes_total', c: 'var(--sii)' },
  ].filter((l) => ser(l.m)).map((l) => ({ data: ser(l.m).points.map((p) => p.value), c: l.c }));

  const derived = (b.derived || []).map((d) => `
    <div style="padding:10px 0;border-bottom:1px solid var(--bd)">
      <div style="display:flex;justify-content:space-between;align-items:baseline;gap:12px">
        <span style="font-size:12px;font-weight:600">${esc(d.label)}</span>
        <span style="font-size:17px;font-weight:800;font-variant-numeric:tabular-nums;white-space:nowrap">
          ${d.value === null ? '—' : fmt(d.value)} <span style="font-size:11px;color:var(--tx2);font-weight:600">${esc(d.unit || '')}</span></span>
      </div>
      <div style="font-size:11px;color:var(--txm);margin-top:4px;line-height:1.55">${esc(d.note)}</div>
    </div>`).join('');

  const caveats = (b.caveats || []).map((c) => `
    <div class="gr" style="border-left-color:var(--cm)"><strong>${esc(c.title)}:</strong> ${esc(c.text)}</div>`).join('');

  const flags = (b.quality_flags || []).map((f) => `
    <div class="banner demo"><strong>Control de calidad · ${esc(f.label)}:</strong> ${esc(f.text)}</div>`).join('');

  const seriesRows = b.series.map((s) => `<tr>
    <td><strong>${esc(s.label)}</strong><br><code class="rut">${esc(s.metric)}</code></td>
    ${s.points.map((p) => `<td class="num">${fmt(p.value)}</td>`).join('')}
    <td><a href="${esc(s.points[s.points.length - 1].source_url)}" target="_blank" rel="noopener"
      style="color:var(--ac);font-size:11px">fuente ↗</a></td>
  </tr>`).join('');

  const topSectors = [...app.data.sectors]
    .filter((s) => s.so_count).sort((a, b2) => b2.so_count - a.so_count).slice(0, 12);

  const gaps = (app.data.sector_gaps || []).map((g) => `<tr>
    <td>${esc(g.registry_label)}</td><td class="num">${fmt(g.so_count)}</td>
    <td><span class="rk md">${esc(g.status)}</span></td></tr>`).join('');

  return `
    <div class="mh"><h1>Benchmark Nacional</h1>
      <p>Producción propia contrastada con el denominador público de la UAF · Equivalente chileno del benchmark contra estadísticas de industria</p></div>
    ${guardrails('benchmark')}
    ${caveats}${flags}
    <div class="krow">
      ${kpi('Universo inscrito', fmt(last('entidades_reportantes_total')?.value), `Sujetos obligados · ${last('entidades_reportantes_total')?.period || ''}`, 'uaf')}
      ${kpi('ROS recibidos', fmt(last('ros_recibidos')?.value), `Nacional · ${last('ros_recibidos')?.period || ''}`, 'acc')}
      ${kpi('Equivalencia de taxonomía', cov.mapped_pct === null ? '—' : `${cov.mapped_pct}%`,
        `${fmt(cov.mapped_entities)} de ${fmt(cov.registry_entities)} entidades`, 'sii')}
      ${kpi('Actividades sin equivalencia', fmt(cov.unmapped_activities), 'Del registro, no forzadas', 'warn')}
    </div>
    <div class="g2">
      <div class="card"><div class="ct">ROS recibidos frente al universo inscrito</div>
        ${lines.length ? linechart(lines, labels, Math.min(W / 2 - 40, 420), 170) : ''}
        <div style="display:flex;gap:14px;margin-top:8px;font-size:11px">
          <span style="color:var(--uaf)">■ ROS recibidos</span>
          <span style="color:var(--sii)">■ Universo inscrito</span></div>
        <div style="margin-top:8px;font-size:11px;color:var(--txm)">
          El universo crece 21,8% entre 2021 y 2025; los ROS, 124,2%. La brecha entre ambas
          pendientes es el hecho a explicar, y admite lecturas opuestas.</div>
      </div>
      <div class="card"><div class="ct">Indicadores derivados</div>${derived}</div>
    </div>
    <div class="card"><div class="ct">Series oficiales publicadas por la UAF</div>
      <div class="scroll-x"><table class="dtbl">
        <thead><tr><th>Métrica</th>${labels.map((l) => `<th class="num">${l}</th>`).join('')}<th>Origen</th></tr></thead>
        <tbody>${seriesRows}</tbody></table></div>
    </div>
    <div class="g2">
      <div class="card"><div class="ct">Universo inscrito por actividad · top 12</div>
        ${hbar(topSectors.map((s) => ({ l: s.name.slice(0, 26), v: s.so_count, c: 'var(--uaf)' })),
          Math.min(W / 2 - 40, 420), 300, 200)}
      </div>
      <div class="card"><div class="ct">Actividades del registro sin equivalencia exacta</div>
        <div class="scroll-x"><table class="dtbl">
          <thead><tr><th>Glosa del registro</th><th class="num">Entidades</th><th>Estado</th></tr></thead>
          <tbody>${gaps}</tbody></table></div>
        <div style="margin-top:10px;font-size:11px;color:var(--txm)">
          El cruce con la taxonomía se hace por igualdad exacta sobre la forma normalizada.
          Estas glosas no se fuerzan a un sector: se reportan como brecha para resolución gobernada.</div>
      </div>
    </div>`;
}

function rCalibracion() {
  const rules = app.data.rules;
  const shown = rules.filter((r) => r.dispositions >= 20);
  const hidden = rules.filter((r) => r.dispositions > 0 && r.dispositions < 20);
  const mute = rules.filter((r) => r.status === 'MUDA');
  const W = contentWidth();

  const rows = shown.map((r) => {
    const mix = Object.entries(r.reason_mix || {})
      .sort((a, b) => b[1] - a[1])
      .map(([k, v]) => `<span class="nxt-s">${REASON_LABEL[k] || k}: ${v}</span>`).join(' ');
    return `<tr>
      <td><code class="mono">${esc(r.rule_id)}</code><br><span style="color:var(--tx2)">${esc(r.label)}</span></td>
      <td>${badge(r.source_id)}</td>
      <td class="num">${fmt(r.dispositions)}</td>
      <td class="num"><span class="rk ${statusRk[r.status] || 'nd'}">${r.non_corroboration_rate}%</span></td>
      <td class="num">${r.escalation_contribution}%</td>
      <td><div style="display:flex;gap:4px;flex-wrap:wrap">${mix}</div></td>
    </tr>`;
  }).join('');

  return `
    <div class="mh"><h1>Calibración de Reglas</h1>
      <p>El desenlace analítico realimenta la regla que originó la señal · Se evalúan reglas y fuentes, nunca personas</p></div>
    ${guardrails('calibracion')}
    <div class="krow">
      ${kpi('Reglas evaluables', fmt(shown.length), '≥20 disposiciones registradas', 'acc')}
      ${kpi('Reglas en crítico', fmt(shown.filter((r) => r.status === 'CRIT').length), 'No corroboración > 70%', 'crit')}
      ${kpi('Reglas mudas', fmt(mute.length), 'Sin señales en 3 períodos', 'warn')}
      ${kpi('Muestra insuficiente', fmt(hidden.length), 'Ocultas hasta alcanzar 20 disposiciones', 'nodata')}
    </div>
    <div class="card"><div class="ct">Tasa de no corroboración por regla</div>
      ${hbar(shown.map((r) => ({
        l: r.rule_id.split('_')[0],
        v: r.non_corroboration_rate,
        suffix: '%',
        c: r.non_corroboration_rate > 70 ? 'var(--cr)' : r.non_corroboration_rate > 40 ? 'var(--cm)' : 'var(--cl)',
      })), Math.min(W - 60, 700), 190, 150)}
      <div style="margin-top:8px;font-size:11px;color:var(--txm)">
        Equivalente funcional de la tasa de falsos positivos, con nombre distinto a propósito:
        una señal no corroborada no era falsa, era insuficiente.
      </div>
    </div>
    <div class="card"><div class="ct">Detalle y diagnóstico por regla</div>
      <div class="scroll-x"><table class="dtbl">
        <thead><tr><th>Regla</th><th>Fuente</th><th class="num">Disposiciones</th>
          <th class="num">No corroboración</th><th class="num">Contribución a escalados</th><th>Mezcla de motivos</th></tr></thead>
        <tbody>${rows}</tbody></table></div>
      <div style="margin-top:12px;font-size:11px;color:var(--txm)">
        Diagnóstico, no puntaje. Predominio de <strong>Error de identidad</strong> indica problema de resolución de entidad;
        predominio de <strong>Explicación legítima</strong> indica umbral mal puesto. Son remedios distintos.
      </div>
    </div>
    ${mute.length ? `<div class="card"><div class="ct">Reglas sin producción</div>
      ${mute.map((r) => `<div style="padding:7px 0;border-bottom:1px solid var(--bd);font-size:12px">
        <code class="mono">${esc(r.rule_id)}</code> · ${esc(r.label)} ${badge(r.source_id)}
      </div>`).join('')}
      <div style="margin-top:10px;font-size:11px;color:var(--txm)">Una regla muda puede estar bien calibrada o estar rota. Requiere revisión, nunca desactivación automática.</div>
    </div>` : ''}`;
}

function rTerritorio() {
  const regions = app.data.territory;
  const sorted = [...regions].sort((a, b) => (b.exposure ?? -1) - (a.exposure ?? -1));
  const sel = regions.find((r) => r.territory_id === app.region) || sorted[0];
  const layers = [
    ['exposure', 'Exposición'], ['crime_art27', 'Delictual art. 27'], ['so_count', 'SO UAF'],
    ['public_spend_mm', 'Gasto público'], ['osfl_count', 'OSFL'],
  ];
  const high = regions.filter((r) => (r.exposure ?? 0) >= 60).length;

  const detail = sel ? `
    <div style="font-size:14px;font-weight:800;margin-bottom:10px;letter-spacing:-.02em">${esc(sel.name)}</div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:12px">
      <div style="background:var(--s2);border-radius:8px;padding:10px;text-align:center">
        <div class="kl">Exposición</div>
        <div style="font-size:22px;font-weight:800;color:${levelVar(sel.exposure)};margin:2px 0">${fmt(sel.exposure)}</div>
        <span class="rk ${level(sel.exposure)}">${levelLabel(sel.exposure)}</span>
      </div>
      <div style="background:var(--s2);border-radius:8px;padding:10px;text-align:center">
        <div class="kl">Casos abiertos</div>
        <div style="font-size:22px;font-weight:800;color:var(--ac);margin:2px 0">${fmt(sel.open_cases)}</div>
        <div style="font-size:10px;color:var(--txm)">en la región</div>
      </div>
    </div>
    <table class="dtbl" style="font-size:11px">
      <tr><td style="color:var(--tx2)">Clave territorial</td><td class="num"><code class="mono">${esc(sel.territory_id)}</code></td></tr>
      <tr><td style="color:var(--tx2)">SO UAF</td><td class="num">${fmt(sel.so_count)}</td></tr>
      <tr><td style="color:var(--tx2)">Delitos art. 27 Ley 19.913</td><td class="num">${fmt(sel.crime_art27)}</td></tr>
      <tr><td style="color:var(--tx2)">Gasto público</td><td class="num">$${fmt(sel.public_spend_mm)}M</td></tr>
      <tr><td style="color:var(--tx2)">OSFL activas</td><td class="num">${fmt(sel.osfl_count)}</td></tr>
      <tr><td style="color:var(--tx2)">Auditorías CGR</td><td class="num">${fmt(sel.cgr_audits)}</td></tr>
    </table>` : '';

  return `
    <div class="mh"><h1>Análisis Territorial</h1>
      <p>Distribución geográfica de señales · 16 regiones · Claves CUT/Subdere del Context Hub</p></div>
    ${guardrails('territorio')}
    <div class="fbr" style="margin-bottom:16px">
      <span style="font-size:12px;color:var(--tx2);font-weight:600">Capa:</span>
      ${layers.map(([k, l]) => `<button class="fbtn${k === app.mapLayer ? ' on' : ''}" data-layer="${k}">${l}</button>`).join('')}
    </div>
    <div class="g12">
      <div>
        <div class="krow" style="margin-bottom:12px">
          ${kpi('Mayor exposición', sorted[0]?.code || '—', `${esc(sorted[0]?.name || '')} · ${fmt(sorted[0]?.exposure)}`, 'crit')}
          ${kpi('En nivel alto', fmt(high), 'Regiones con exposición ≥60', 'warn')}
        </div>
        <div class="card"><div class="ct">Exposición por región</div>
          ${sorted.map((r) => `<div class="rrow">
            <div class="rname"><strong>${esc(r.code)}</strong> <span style="color:var(--tx2)">${esc(r.name)}</span></div>
            <div class="rbw"><div class="pb"><div class="pf" style="width:${r.exposure ?? 0}%;background:${levelVar(r.exposure ?? 0)}"></div></div></div>
            <div class="rval" style="color:${levelVar(r.exposure ?? 0)}">${fmt(r.exposure)}</div>
            <div class="rct">${fmt(r.open_cases)} casos</div>
          </div>`).join('')}
        </div>
      </div>
      <div>
        <div class="card"><div class="ct">Mapa de Chile · selecciona una región</div>
          <div style="display:flex;gap:16px;align-items:flex-start">
            <div id="mapa-container">${chileMap(regions, app.mapLayer, app.region)}</div>
            <div id="reg-detail" style="flex:1;min-width:0">${detail}</div>
          </div>
        </div>
      </div>
    </div>`;
}

function rSectorial() {
  const sectors = app.data.sectors;
  const present = sectors.filter((s) => s.so_count);
  const absent = sectors.filter((s) => !s.so_count);
  const totalSO = present.reduce((a, s) => a + s.so_count, 0);
  const mapped = sectors.filter((s) => s.acteco_strong_mappings).length;
  const W = contentWidth();

  // Concentración: cuántas actividades acumulan la mitad del universo inscrito.
  const ranked = [...present].sort((a, b) => b.so_count - a.so_count);
  let acc = 0;
  const half = ranked.findIndex((s) => (acc += s.so_count) >= totalSO / 2) + 1;

  const rows = sectors.map((s) => `<tr>
    <td>${esc(s.name)}<br><code class="rut">${esc(s.sector_id)}</code></td>
    <td style="font-size:11px;color:var(--tx2)">${esc(s.macrofamily || '—')}</td>
    <td class="num">${s.so_count === null ? '<span class="nodata-cell">no inscritas</span>' : fmt(s.so_count)}</td>
    <td class="num">${s.so_count ? `${(s.so_count / totalSO * 100).toFixed(1)}%` : '<span class="nodata-cell">—</span>'}</td>
    <td class="num">${s.acteco_mappings === null ? '<span class="nodata-cell">—</span>' : fmt(s.acteco_mappings)}</td>
    <td class="num">${s.acteco_strong_mappings === null ? '<span class="nodata-cell">—</span>' : fmt(s.acteco_strong_mappings)}</td>
    <td class="num nodata-cell">—</td></tr>`).join('');

  const byFamily = Object.entries(present.reduce((m, s) => {
    const k = s.macrofamily || 'Sin familia';
    return { ...m, [k]: (m[k] || 0) + s.so_count };
  }, {})).sort((a, b) => b[1] - a[1]);
  const famColors = ['var(--uaf)', 'var(--sii)', 'var(--cgr)', 'var(--pre)', 'var(--san)', 'var(--osl)', 'var(--del)', 'var(--ctx)'];

  return `
    <div class="mh"><h1>Actividad Sectorial</h1>
      <p>Universo inscrito por actividad UAF · Registro real cruzado con la taxonomía del Context Hub</p></div>
    ${guardrails('sectorial')}
    <div class="gr" style="border-left-color:var(--cm)"><strong>Alcance de esta vista:</strong>
      muestra el <strong>universo inscrito</strong>, que es un hecho registral. La UAF no publica ROS,
      ROE ni sanciones desagregados por actividad, de modo que las columnas de reportabilidad se
      serializan NO_DATA y se muestran «—». El contraste disponible es nacional y vive en
      <strong>Benchmark</strong>.</div>
    <div class="krow">
      ${kpi('Sujetos obligados inscritos', fmt(totalSO), `En ${present.length} actividades del registro`, 'uaf')}
      ${kpi('Actividades en la taxonomía', fmt(sectors.length), `${absent.length} sin entidades inscritas`, 'acc')}
      ${kpi('Concentración', `${half} act.`, 'Acumulan la mitad del universo', 'crit')}
      ${kpi('Con crosswalk MATCH_FUERTE', fmt(mapped), 'Actividades con equivalencia ACTECO fuerte', 'sii')}
    </div>
    <div class="g2">
      <div class="card"><div class="ct">Universo inscrito por actividad · top 12</div>
        ${hbar(ranked.slice(0, 12).map((s) => ({ l: s.name.slice(0, 26), v: s.so_count, c: 'var(--uaf)' })),
          Math.min(W / 2 - 40, 420), 300, 195)}
      </div>
      <div class="card" style="display:flex;flex-direction:column;align-items:center">
        <div class="ct" style="width:100%">Universo por macrofamilia</div>
        ${donut(byFamily.map(([l, v], i) => ({ l: l.length > 26 ? `${l.slice(0, 26)}…` : l, v, c: famColors[i % famColors.length] })), 180, 180, 'SO')}
      </div>
    </div>
    <div class="card"><div class="ct">Detalle por actividad UAF</div>
      <div class="scroll-x"><table class="dtbl">
        <thead><tr><th>Actividad</th><th>Macrofamilia</th><th class="num">SO inscritos</th>
          <th class="num">Share</th><th class="num">Mapeos ACTECO</th><th class="num">MATCH_FUERTE</th>
          <th class="num">% ROS</th></tr></thead>
        <tbody>${rows}</tbody></table></div>
    </div>`;
}

function rAnomalias() {
  const kindLabel = {
    ANOMALIA_CONTEXTUAL: ['Anomalía contextual', 'pre'],
    ALERTA_FISCALIZACION: ['Alerta de fiscalización', 'cgr'],
    SENAL_AML: ['Señal AML', 'uaf'],
  };
  const counts = Object.keys(kindLabel).map((k) => app.data.anomalies.filter((a) => a.kind === k).length);
  const affected = app.data.anomalies.reduce((a, b) => a + (b.affected_count || 0), 0);

  const cards = app.data.anomalies.map((a) => {
    const [lbl, tok] = kindLabel[a.kind];
    return `<div class="ac">
      <div class="ah">
        <div>
          <div class="at">${esc(a.title)}</div>
          <div style="margin-top:6px;display:flex;gap:5px;flex-wrap:wrap;align-items:center">
            ${a.source_ids.map(badge).join('')}
            <span class="bd ${tok}">${lbl}</span>
            ${a.corroborated ? '<span class="rk lo">Corroborada</span>' : '<span class="rk md">Sin corroborar</span>'}
          </div>
        </div>
        <div style="text-align:right;flex-shrink:0;margin-left:14px">
          <div style="font-size:26px;font-weight:800;color:var(--${tok});line-height:1">${fmt(a.affected_count)}</div>
          <div style="font-size:10px;color:var(--txm)">entidades</div>
        </div>
      </div>
      <div class="adesc">${esc(a.description)}</div>
      <div class="aev">📎 ${esc(a.evidence)} · <code class="mono">${esc(a.rule_id)}</code></div>
    </div>`;
  }).join('');

  return `
    <div class="mh"><h1>Anomalías Detectadas</h1>
      <p>Patrones contextuales que requieren corroboración antes de elevarse a señal gobernada</p></div>
    ${guardrails('anomalias')}
    <div class="krow">
      ${kpi('Anomalías contextuales', fmt(counts[0]), 'Requieren corroboración', 'pre')}
      ${kpi('Alertas de fiscalización', fmt(counts[1]), 'No son señales AML', 'cgr')}
      ${kpi('Señales AML', fmt(counts[2]), 'Con evidencia directa', 'uaf')}
      ${kpi('Entidades afectadas', fmt(affected), 'En revisión activa', 'acc')}
    </div>${cards}`;
}

function rAml360() {
  const c = app.data.cases.find((x) => x.case_id === app.entityFilter) || app.data.cases[0];
  const cls = level(c.score.score_value);
  const sources = [...new Set(c.signals.map((s) => s.source_id))];
  const W = contentWidth();
  const options = app.data.cases.map((x) =>
    `<option value="${esc(x.case_id)}"${x.case_id === c.case_id ? ' selected' : ''}>${esc(x.name)}</option>`).join('');

  return `
    <div class="mh"><h1>AML 360°</h1>
      <p>Vista integrada de señales, convergencia, relaciones y evidencia por entidad</p></div>
    ${guardrails('aml360')}
    <div class="card"><div class="fbr">
      <select class="fsel" id="entity-select" style="min-width:280px">${options}</select>
      <span style="font-size:11px;color:var(--txm)">${c.entity_id ? `Identidad canónica: <code class="mono">${esc(c.entity_id)}</code>` : 'Identidad no resuelta · ENTITY_ID_NULL_CANDIDATE_ONLY'}</span>
    </div></div>
    <div class="card" style="border-top:2px solid ${levelVar(c.score.score_value)}">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:14px">
        <div>
          <h2 style="font-size:16px;font-weight:800;letter-spacing:-.03em">${esc(c.name)}</h2>
          <div style="color:var(--tx2);font-size:12px;margin-top:2px">
            ${c.rut ? `RUT <code class="rut">${esc(c.rut)}</code>` : 'Sin RUT en la fuente'} · ${esc(c.entity_type)} · ${esc(c.region_label)}</div>
          <div style="margin-top:8px;display:flex;gap:5px;flex-wrap:wrap;align-items:center">
            <span class="st ${c.state}">${STATE_LABEL[c.state]}</span>${sources.map(badge).join('')}</div>
        </div>
        <div style="text-align:center">${gauge(c.score.score_value)}
          <div style="margin-top:4px"><span class="rk ${cls}">${levelLabel(c.score.score_value)}</span></div></div>
      </div>
      <div class="g3" style="margin-bottom:13px">
        <div style="background:var(--cr-bg);border-radius:8px;padding:12px;text-align:center">
          <div class="kl" style="color:var(--cr)">Señales directas</div>
          <div style="font-size:26px;font-weight:800;color:var(--cr);margin:4px 0">${c.signals.length}</div></div>
        <div style="background:var(--cm-bg);border-radius:8px;padding:12px;text-align:center">
          <div class="kl" style="color:var(--cm)">Fuentes independientes</div>
          <div style="font-size:26px;font-weight:800;color:var(--cm);margin:4px 0">${sources.length}</div></div>
        <div style="background:var(--uaf-bg);border-radius:8px;padding:12px;text-align:center">
          <div class="kl" style="color:var(--uaf)">Referencias de evidencia</div>
          <div style="font-size:26px;font-weight:800;color:var(--uaf);margin:4px 0">${c.signals.flatMap((s) => s.evidence_refs).length}</div></div>
      </div>
      <div class="sigs" style="margin-bottom:12px">${c.signals.map(signalChip).join('')}</div>
      <div class="hyp"><div class="hyp-lbl">Hipótesis analítica</div><div class="hyp-tx">${esc(c.hypothesis)}</div></div>
      <div class="g2" style="margin-top:14px">
        <div><div class="ct">Contribución de cada fuente a la prioridad</div>
          ${hbar(c.signals.map((s) => ({ l: srcLabel(s.source_id), v: s.weight, c: `var(--${s.source_id})` })),
            Math.min(W / 2 - 40, 360), 150, 90)}
          <div style="margin-top:8px;font-size:11px;color:var(--txm)">La contribución es trazable a la regla que la produjo.</div>
        </div>
        <div><div class="ct">Evidencia por señal</div>
          ${c.signals.map((s) => `<div style="padding:6px 0;border-bottom:1px solid var(--bd);font-size:11px">
            <code class="mono">${esc(s.rule_id)}</code><br>
            ${s.evidence_refs.map((e) => `<span class="chip">${esc(e)}</span>`).join(' ')}</div>`).join('')}
        </div>
      </div>
      ${c.next_steps?.length ? `<div style="margin-top:14px">
        <div class="ct">Próximos pasos</div>
        ${c.next_steps.map((s) => `<div style="padding:6px 0;font-size:12px;border-bottom:1px solid var(--bd);color:var(--tx2)">→ ${esc(s)}</div>`).join('')}
      </div>` : ''}
    </div>`;
}

function rRed() {
  const { nodes, edges } = app.data.network;
  const relLabel = {
    REPRESENTANTE_LEGAL: 'Representante legal', DOMICILIO_COMPARTIDO: 'Domicilio compartido',
    PROVEEDOR_COMUN: 'Proveedor común', ORGANISMO_CONTRATANTE: 'Organismo contratante',
    PROPIEDAD: 'Propiedad', CANDIDATO_BF: 'Beneficiario final candidato',
  };
  const byId = Object.fromEntries(nodes.map((n) => [n.node_id, n.label]));
  const rows = edges.map((e) => `<tr>
    <td>${esc(byId[e.from])}</td><td>${esc(byId[e.to])}</td>
    <td>${esc(relLabel[e.relation] || e.relation)}</td>
    <td>${e.confirmed ? '<span class="rk lo">Confirmado</span>' : '<span class="rk md">Candidato</span>'}</td>
    <td>${e.evidence_refs.map((r) => `<span class="chip">${esc(r)}</span>`).join(' ')}</td>
  </tr>`).join('');

  return `
    <div class="mh"><h1>Red de Relaciones</h1>
      <p>Expansión sobre vínculos observados · Sin herencia de riesgo entre nodos</p></div>
    ${guardrails('red')}
    <div class="card" style="padding:8px">${networkGraph(nodes, edges)}</div>
    <div class="card"><div class="ct">Vínculos y su evidencia</div>
      <div class="scroll-x"><table class="dtbl">
        <thead><tr><th>Origen</th><th>Destino</th><th>Relación</th><th>Estado</th><th>Evidencia</th></tr></thead>
        <tbody>${rows}</tbody></table></div>
    </div>`;
}

function rEvidencia() {
  const keys = [
    ['entity_id', 'Identidad canónica de la entidad (RUT con dígito verificador validado)'],
    ['territory_id', 'CL-REG / CL-PROV / CL-COM según CUT/Subdere'],
    ['sector_id', 'UAF-SEC-NN · 55 actividades UAF conformadas'],
    ['period_id', 'Período canónico de la señal'],
    ['source_id', 'Fuente y versión del dato'],
  ];
  const rows = app.data.sources.map((s) => `<tr>
    <td><strong>${esc(s.label)}</strong></td>
    <td>${esc(s.coverage)}</td><td>${esc(s.update_cadence)}</td>
    <td class="num">${s.exports.length}</td>
    <td><span class="rk ${statusRk[s.status]}">${s.status}</span></td>
    <td><div style="display:flex;flex-direction:column;gap:2px">
      ${s.exports.slice(0, 3).map((e) => `<code class="mono" style="font-size:10px">${esc(e)}</code>`).join('')}
      ${s.exports.length > 3 ? `<span style="font-size:10px;color:var(--txm)">+${s.exports.length - 3} más</span>` : ''}
    </div></td>
  </tr>`).join('');

  return `
    <div class="mh"><h1>Evidencia y Trazabilidad</h1>
      <p>Cobertura, fuente y linaje de todas las señales · Principio evidence-first</p></div>
    ${guardrails('evidencia')}
    <div class="krow">
      ${kpi('Integridad de evidencia', metricValue('PRG_EVIDENCE_INTEGRITY'), 'Señales con referencia resoluble', 'ok')}
      ${kpi('Resolución de identidad', metricValue('PRG_IDENTITY_RESOLUTION'), 'Cobertura de entity_id conformado', 'sii')}
      ${kpi('Cobertura territorial', metricValue('PRG_TERRITORY_COVERAGE'), 'Cobertura de territory_id conformado', 'cgr')}
      ${kpi('Cobertura sectorial', metricValue('PRG_SECTOR_COVERAGE'), 'Cobertura de sector_id conformado', 'uaf')}
    </div>
    <div class="card"><div class="ct">Catálogo de fuentes y artefactos publicados</div>
      <div class="scroll-x"><table class="dtbl">
        <thead><tr><th>Fuente</th><th>Cobertura</th><th>Actualización</th><th class="num">Exports</th><th>Estado</th><th>Artefactos</th></tr></thead>
        <tbody>${rows}</tbody></table></div>
    </div>
    <div class="card"><div class="ct">Claves conformadas del ecosistema</div>
      ${keys.map(([k, d]) => `<div style="padding:7px 0;border-bottom:1px solid var(--bd);font-size:12px">
        <span class="chip">${k}</span> <span style="color:var(--tx2)">${esc(d)}</span></div>`).join('')}
      <div style="margin-top:13px;font-size:11px;color:var(--txm)">
        Las anomalías y alertas de fiscalización <strong>no modifican</strong>
        <code class="mono">signals.jsonl</code> ni <code class="mono">scores.jsonl</code>:
        son objetos semánticos distintos de la señal AML gobernada.
      </div>
    </div>`;
}

function rFiscal() {
  const sectors = app.data.sectors;
  const present = sectors.filter((s) => s.so_count);
  const totalSO = present.reduce((a, s) => a + s.so_count, 0);
  const strongMaps = sectors.reduce((a, s) => a + (s.acteco_strong_mappings || 0), 0);
  const b = app.data.benchmark;
  const supervision = b.series?.find((s) => s.metric === 'acciones_supervision');
  const lastSup = supervision?.points[supervision.points.length - 1];
  const W = contentWidth();

  return `
    <div class="mh"><h1>Perímetro UAF · Fiscalización</h1>
      <p>Universo inscrito y equivalencias hacia ACTECO · Registro real de sujetos obligados</p></div>
    ${guardrails('fiscal')}
    <div class="krow">
      ${kpi('Sujetos obligados inscritos', fmt(totalSO), `${present.length} actividades con registro`, 'uaf')}
      ${kpi('Equivalencias MATCH_FUERTE', fmt(strongMaps), 'Hacia ACTECO del SII · candidatas a validación', 'sii')}
      ${kpi('Acciones de supervisión', fmt(lastSup?.value), `Nacional · ${lastSup?.period || ''}`, 'cgr')}
      ${kpi('MATCH_FUERTE sin inscripción', '—', 'Requiere cruzar el padrón SII completo', 'nodata')}
    </div>
    <div class="gr" style="border-left-color:var(--cm)"><strong>Pendiente de la fase F2:</strong>
      detectar entidades con actividad ACTECO de MATCH_FUERTE que <em>no</em> figuran en el registro
      UAF exige cruzar el padrón completo del SII contra la nómina, y hoy Radar SII declara
      <code class="mono">sector</code> sin bloque conformado. Hasta entonces el indicador es NO_DATA
      y no se estima.</div>
    <div class="g2">
      <div class="card"><div class="ct">Densidad de equivalencias ACTECO por actividad</div>
        ${hbar(sectors.filter((s) => s.acteco_mappings)
          .sort((a, c) => c.acteco_mappings - a.acteco_mappings).slice(0, 12)
          .map((s) => ({ l: s.name.slice(0, 26), v: s.acteco_mappings, c: 'var(--sii)' })),
          Math.min(W / 2 - 40, 420), 290, 195)}
      </div>
      <div class="card"><div class="ct">Acciones de supervisión · serie nacional</div>
        ${supervision ? vbar(supervision.points.map((p) => ({ l: p.period, v: p.value, c: 'var(--cgr)' })),
          Math.min(W / 2 - 40, 380), 210) : ''}
        <div style="margin-top:8px;font-size:11px;color:var(--txm)">
          La capacidad de supervisión se mantiene plana mientras el universo inscrito crece:
          172 acciones en 2025 sobre 9.911 entidades. Es un hecho de contexto, no un juicio.</div>
      </div>
    </div>`;
}

function rSanciones() {
  const s = app.data.sanctions;
  const alacft = s.filter((x) => x.alacft).length;
  const repeat = s.filter((x) => x.repeat_offender).length;
  const pending = s.filter((x) => !x.resolved).length;
  const unresolvedId = s.filter((x) => !x.entity_id).length;

  const rows = s.map((x) => `<tr>
    <td><strong>${esc(x.entity_name)}</strong><br>
      ${x.rut ? `<code class="rut">${esc(x.rut)}</code>` : '<span class="nodata-cell">identidad pendiente</span>'}</td>
    <td>${esc(x.authority)}</td>
    <td>${esc(x.matter)} ${x.alacft ? '<span class="bd uaf">ALA/CFT</span>' : ''}</td>
    <td class="num">${esc(x.date)}</td>
    <td class="num">${x.amount ? esc(x.amount) : '<span class="nodata-cell">—</span>'}</td>
    <td>${x.repeat_offender ? '<span class="rk cr">Reincidente</span>' : '<span class="rk lo">1ª vez</span>'}</td>
    <td>${x.resolved ? '<span class="rk lo">Resuelto</span>' : '<span class="rk hi">Activo</span>'}</td>
  </tr>`).join('');

  const byAuthority = Object.entries(s.reduce((acc, x) =>
    ({ ...acc, [x.authority]: (acc[x.authority] || 0) + 1 }), {}))
    .map(([l, v], i) => ({ l, v, c: ['var(--cgr)', 'var(--uaf)', 'var(--sii)', 'var(--san)', 'var(--nd)'][i % 5] }));

  return `
    <div class="mh"><h1>Registro de Sanciones</h1>
      <p>Eventos adversos regulatorios por supervisor prudencial · Con resolución de identidad</p></div>
    ${guardrails('sanciones')}
    <div class="krow">
      ${kpi('Total de sanciones', fmt(s.length), 'En el período', 'san')}
      ${kpi('Vinculadas ALA/CFT', fmt(alacft), `${Math.round((alacft / s.length) * 100)}% del total`, 'crit')}
      ${kpi('Reincidentes', fmt(repeat), 'Con ≥2 eventos adversos', 'warn')}
      ${kpi('Procesos activos', fmt(pending), 'Sin resolución definitiva', 'acc')}
      ${kpi('Identidad pendiente', fmt(unresolvedId), 'Sin RUT en la fuente de origen', 'nodata')}
    </div>
    <div class="g21">
      <div class="card"><div class="ct">Registro detallado</div>
        <div class="scroll-x"><table class="dtbl">
          <thead><tr><th>Entidad</th><th>Autoridad</th><th>Materia</th><th class="num">Fecha</th>
            <th class="num">Monto</th><th>Reincidencia</th><th>Estado</th></tr></thead>
          <tbody>${rows}</tbody></table></div>
      </div>
      <div class="card" style="display:flex;flex-direction:column;align-items:center">
        <div class="ct" style="width:100%">Por autoridad sancionadora</div>
        ${donut(byAuthority, 155, 155, 'sanciones')}
      </div>
    </div>`;
}

function rPerfil() {
  return `
    <div class="mh"><h1>Perfil por RUT</h1>
      <p>Función secundaria · Para hipótesis sobre una entidad ya identificada</p></div>
    <div class="gr">Para exploración sin hipótesis previa, use el <strong>Motor de Hallazgos</strong>
      o la vista <strong>Territorial</strong>. Esta vista es complementaria.</div>
    ${rAml360().split('</div>').slice(3).join('</div>')}`;
}

const RENDERERS = {
  hallazgos: rHallazgos, casos: rCasos, territorio: rTerritorio, sectorial: rSectorial,
  anomalias: rAnomalias, aml360: rAml360, red: rRed, evidencia: rEvidencia,
  salud: rSalud, benchmark: rBenchmark, calibracion: rCalibracion,
  fiscal: rFiscal, sanciones: rSanciones, perfil: rPerfil,
};

/* ── Navegación y arranque ──────────────────────────────────── */

function renderNav() {
  const mods = PERSONAS[app.persona].mods;
  const openCases = app.data.cases.filter((c) => OPEN_STATES.includes(c.state)).length;
  const crit = app.data.program_health.filter((m) => m.status === 'CRIT').length;
  const groups = [];
  mods.forEach((id) => {
    const m = MODULES[id];
    let g = groups.find((x) => x.name === m.g);
    if (!g) groups.push((g = { name: m.g, items: [] }));
    g.items.push(id);
  });

  $('nav').innerHTML = groups.map((g) => `<div class="nav-sec">
    <div class="nav-lbl">${g.name}</div>
    ${g.items.map((id) => {
      const m = MODULES[id];
      const bdg = id === 'casos' && openCases
        ? `<span class="ni-bd">${openCases}</span>`
        : id === 'salud' && crit ? `<span class="ni-bd warn">${crit}</span>` : '';
      return `<button class="ni${id === app.module ? ' on' : ''}" data-mod="${id}">
        <span class="ni-ic">${m.ic}</span><span>${m.t}</span>${bdg}</button>`;
    }).join('')}
  </div>`).join('');
}

function render() {
  renderNav();
  $('tb-title').textContent = MODULES[app.module].t;
  const body = (RENDERERS[app.module] || rHallazgos)();
  // El aviso de procedencia va tras el encabezado, antes de cualquier cifra.
  const banner = provenanceBanner(app.module);
  $('ct').innerHTML = banner
    ? body.replace(/(<\/div>)/, `$1${banner}`)
    : body;
  $('ct').scrollTop = 0;
}

function go(moduleId) {
  if (!MODULES[moduleId]) return;
  app.module = moduleId;
  render();
}

function bindEvents() {
  $('sb').addEventListener('click', (e) => {
    const btn = e.target.closest('[data-mod]');
    if (btn) go(btn.dataset.mod);
  });

  $('ct').addEventListener('click', (e) => {
    const layer = e.target.closest('[data-layer]');
    if (layer) { app.mapLayer = layer.dataset.layer; render(); return; }
    const region = e.target.closest('[data-region]');
    if (region) { app.region = region.dataset.region; render(); }
  });

  $('ct').addEventListener('change', (e) => {
    if (e.target.id === 'entity-select') {
      app.entityFilter = e.target.value;
      render();
    }
  });

  $('persona').addEventListener('change', (e) => {
    app.persona = e.target.value;
    app.module = PERSONAS[app.persona].home;
    render();
  });

  $('theme').addEventListener('click', () => {
    const root = document.documentElement;
    const dark = root.getAttribute('data-theme') !== 'light';
    root.setAttribute('data-theme', dark ? 'light' : 'dark');
    render(); // los gráficos SVG resuelven color en el momento del dibujo
  });
}

async function boot() {
  $('persona').innerHTML = Object.entries(PERSONAS)
    .map(([k, v]) => `<option value="${k}">${v.label}</option>`).join('');

  try {
    const res = await fetch(CONTRACT_URL);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    app.data = await res.json();
  } catch (err) {
    $('ct').innerHTML = `<div class="banner err">
      <strong>No se pudo cargar el contrato.</strong>
      La aplicación consume <code class="mono">app/data/cockpit_contract_v1.json</code> por fetch,
      que el navegador bloquea al abrir el archivo con <code class="mono">file://</code>.
      Levante un servidor estático desde la raíz del repositorio:<br><br>
      <code class="mono">python3 -m http.server 8000</code> y abra
      <code class="mono">http://localhost:8000/app/</code><br><br>
      Detalle: ${esc(err.message)}</div>`;
    return;
  }

  $('brand-ver').textContent = `Corte ${app.data.period_id} · contrato v${app.data.contract_version}`;
  bindEvents();
  render();
}

boot();
