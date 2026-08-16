/* Primitivas de visualización en SVG puro, sin dependencias externas.
   Todas devuelven cadenas de marcado y toman color desde las custom properties,
   de modo que el cambio de tema no exige volver a dibujar. */

let seq = 0;
const uid = () => `g${(seq += 1)}`;

export const fmt = (n) =>
  n === null || n === undefined || Number.isNaN(n) ? '—' : n.toLocaleString('es-CL');

/** Nivel del score de prioridad. Ver KRI_PRIORITY_SCORE en el catálogo. */
export const level = (s) => (s >= 80 ? 'cr' : s >= 60 ? 'hi' : s >= 40 ? 'md' : 'lo');
export const levelLabel = (s) => (s >= 80 ? 'Crítico' : s >= 60 ? 'Alto' : s >= 40 ? 'Medio' : 'Bajo');
export const levelVar = (s) => `var(--${s >= 80 ? 'cr' : s >= 60 ? 'ch' : s >= 40 ? 'cm' : 'cl'})`;

/** Color resuelto en tiempo real, para atributos SVG que no aceptan var(). */
export function cssColor(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || '#888';
}

export function gauge(score, size = 56) {
  const col = levelVar(score);
  const r = size / 2 - 6;
  const c = size / 2;
  const perim = 2 * Math.PI * r;
  const dash = (score / 100) * perim;
  return `<svg width="${size}" height="${size}" role="img" aria-label="Prioridad ${score} de 100">
<circle cx="${c}" cy="${c}" r="${r}" fill="none" stroke="var(--bd)" stroke-width="4.5"/>
<circle cx="${c}" cy="${c}" r="${r}" fill="none" stroke="${col}" stroke-width="4.5"
  stroke-dasharray="${dash.toFixed(1)} ${perim.toFixed(1)}"
  stroke-dashoffset="${(perim * 0.25).toFixed(1)}" stroke-linecap="round"
  transform="rotate(-90 ${c} ${c})"/>
<text x="${c}" y="${c + 5}" text-anchor="middle" font-size="13" font-weight="800"
  fill="${col}" font-family="system-ui,sans-serif">${score}</text></svg>`;
}

export function sparkline(data, w, h, color) {
  const clean = data.filter((v) => v !== null && v !== undefined);
  if (clean.length < 2) return '';
  const max = Math.max(...clean);
  const min = Math.min(...clean);
  const range = max - min || 1;
  const pts = clean
    .map((v, i) => `${(i / (clean.length - 1)) * w},${h - ((v - min) / range) * (h - 4) - 2}`)
    .join(' ');
  const id = uid();
  return `<svg width="${w}" height="${h}" style="display:block" aria-hidden="true">
<defs><linearGradient id="${id}" x1="0" y1="0" x2="0" y2="1">
<stop offset="0%" stop-color="${color}" stop-opacity=".25"/>
<stop offset="100%" stop-color="${color}" stop-opacity="0"/></linearGradient></defs>
<polyline points="${pts} ${w},${h} 0,${h}" fill="url(#${id})" stroke="none"/>
<polyline points="${pts}" stroke="${color}" stroke-width="1.5" fill="none"
  stroke-linecap="round" stroke-linejoin="round"/></svg>`;
}

export function donut(segs, W, H, label) {
  const usable = segs.filter((s) => s.v > 0);
  if (!usable.length) return `<div class="nodata-cell" style="padding:20px">Sin datos</div>`;
  const cx = W / 2;
  const cy = H / 2;
  const r = Math.min(W, H) / 2 - 6;
  const ri = r * 0.58;
  const total = usable.reduce((a, s) => a + s.v, 0);
  const gap = 0.04;
  let angle = -Math.PI / 2;
  let paths = '';
  let legend = '';
  usable.forEach((s) => {
    const slice = (s.v / total) * (2 * Math.PI - gap * usable.length);
    const a1 = angle + gap / 2;
    const a2 = a1 + slice;
    const p = (rad, a) => [cx + rad * Math.cos(a), cy + rad * Math.sin(a)];
    const [x1, y1] = p(r, a1);
    const [x2, y2] = p(r, a2);
    const [x3, y3] = p(ri, a2);
    const [x4, y4] = p(ri, a1);
    const lg = slice > Math.PI ? 1 : 0;
    paths += `<path d="M${x1.toFixed(1)},${y1.toFixed(1)} A${r},${r} 0 ${lg},1 ${x2.toFixed(1)},${y2.toFixed(1)} L${x3.toFixed(1)},${y3.toFixed(1)} A${ri},${ri} 0 ${lg},0 ${x4.toFixed(1)},${y4.toFixed(1)} Z" fill="${s.c}"/>`;
    angle += slice + gap;
    legend += `<span style="display:inline-flex;align-items:center;gap:4px;font-size:10px;color:var(--tx2)">
<span style="width:8px;height:8px;border-radius:2px;background:${s.c};display:inline-block;flex-shrink:0"></span>${s.l}</span>`;
  });
  return `<div style="display:flex;flex-direction:column;align-items:center">
<svg width="${W}" height="${H}">${paths}
<text x="${cx}" y="${cy - 6}" text-anchor="middle" font-size="20" font-weight="800" fill="var(--tx)" font-family="system-ui,sans-serif">${total}</text>
<text x="${cx}" y="${cy + 12}" text-anchor="middle" font-size="10" fill="var(--tx2)" font-family="system-ui,sans-serif">${label}</text></svg>
<div style="display:flex;flex-wrap:wrap;gap:8px;justify-content:center;margin-top:6px">${legend}</div></div>`;
}

export function hbar(data, w, h, lw = 140) {
  if (!data.length) return '';
  const maxV = Math.max(...data.map((d) => d.v)) || 1;
  const rh = h / data.length;
  let s = '';
  data.forEach((d, i) => {
    const y = i * rh;
    const bw = Math.max(2, (d.v / maxV) * (w - lw - 52));
    s += `<text x="0" y="${y + rh * 0.65}" font-size="11" fill="var(--tx2)" font-family="system-ui,sans-serif">${d.l}</text>`;
    s += `<rect x="${lw}" y="${y + rh * 0.25}" width="${bw}" height="${rh * 0.5}" fill="${d.c || 'var(--ac)'}" rx="3"/>`;
    s += `<text x="${lw + bw + 5}" y="${y + rh * 0.65}" font-size="10" fill="var(--tx)" font-weight="700" font-variant-numeric="tabular-nums" font-family="system-ui,sans-serif">${fmt(d.v)}${d.suffix || ''}</text>`;
  });
  return `<svg width="${w}" height="${h}" style="overflow:visible;display:block">${s}</svg>`;
}

export function vbar(data, w, h) {
  if (!data.length) return '';
  const pad = 20;
  const iW = w - pad * 2;
  const iH = h - 28;
  const maxV = Math.max(...data.map((d) => d.v)) * 1.08 || 1;
  const bw = Math.max(8, iW / data.length - 6);
  let s = '';
  [0.33, 0.66, 1].forEach((f) => {
    const y = 8 + iH - f * iH;
    s += `<line x1="${pad}" y1="${y}" x2="${pad + iW}" y2="${y}" stroke="var(--bd)" stroke-width="1"/>`;
  });
  data.forEach((d, i) => {
    const bh = Math.max(2, (d.v / maxV) * iH);
    const x = pad + i * (iW / data.length) + (iW / data.length - bw) / 2;
    const y = 8 + iH - bh;
    const id = uid();
    s += `<defs><linearGradient id="${id}" x1="0" y1="0" x2="0" y2="1">
<stop offset="0%" stop-color="${d.c || 'var(--ac)'}" stop-opacity="1"/>
<stop offset="100%" stop-color="${d.c || 'var(--ac)'}" stop-opacity=".5"/></linearGradient></defs>`;
    s += `<rect x="${x}" y="${y}" width="${bw}" height="${bh}" fill="url(#${id})" rx="4"/>`;
    s += `<text x="${x + bw / 2}" y="${8 + iH + 16}" text-anchor="middle" font-size="9" fill="var(--tx2)" font-family="system-ui,sans-serif">${d.l}</text>`;
    s += `<text x="${x + bw / 2}" y="${y - 4}" text-anchor="middle" font-size="9" fill="var(--tx)" font-weight="700" font-family="system-ui,sans-serif">${d.v}</text>`;
  });
  return `<svg width="${w}" height="${h}" style="display:block">${s}</svg>`;
}

export function linechart(datasets, labels, w, h) {
  const pl = 32;
  const pr = 8;
  const pt = 10;
  const pb = 22;
  const iW = w - pl - pr;
  const iH = h - pt - pb;
  const allV = datasets.flatMap((d) => d.data).filter((v) => v !== null);
  const maxV = Math.max(...allV) * 1.12 || 1;
  const n = labels.length;
  const px = (i) => pl + (i / (n - 1)) * iW;
  const py = (v) => pt + iH - (v / maxV) * iH;
  let s = '';
  [0.25, 0.5, 0.75, 1].forEach((f) => {
    const y = py(maxV * f);
    s += `<line x1="${pl}" y1="${y}" x2="${pl + iW}" y2="${y}" stroke="var(--bd)" stroke-width="1" stroke-dasharray="3,4"/>`;
    s += `<text x="${pl - 5}" y="${y + 4}" text-anchor="end" font-size="8" fill="var(--txm)" font-family="system-ui,sans-serif">${Math.round(maxV * f)}</text>`;
  });
  datasets.forEach((ds) => {
    const pts = ds.data.map((v, i) => ({ x: px(i), y: py(v) }));
    const line = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ');
    const area = `${line} L${px(n - 1).toFixed(1)},${(pt + iH).toFixed(1)} L${px(0).toFixed(1)},${(pt + iH).toFixed(1)} Z`;
    const id = uid();
    s += `<defs><linearGradient id="${id}" x1="0" y1="0" x2="0" y2="1">
<stop offset="0%" stop-color="${ds.c}" stop-opacity=".2"/>
<stop offset="100%" stop-color="${ds.c}" stop-opacity="0"/></linearGradient></defs>`;
    s += `<path d="${area}" fill="url(#${id})"/>`;
    s += `<path d="${line}" stroke="${ds.c}" stroke-width="2" fill="none" stroke-linejoin="round"/>`;
    const last = pts[pts.length - 1];
    s += `<circle cx="${last.x}" cy="${last.y}" r="3.5" fill="${ds.c}"/>`;
  });
  labels.forEach((l, i) => {
    s += `<text x="${px(i).toFixed(1)}" y="${h - 4}" text-anchor="middle" font-size="8.5" fill="var(--txm)" font-family="system-ui,sans-serif">${l}</text>`;
  });
  return `<svg width="${w}" height="${h}" style="display:block">${s}</svg>`;
}

/* Mapa de Chile. Las alturas aproximan la proporción norte-sur real de cada
   región, de modo que la lectura visual no distorsione el territorio. */
const CGEO = [
  { id: 'CL-REG-15', y: 0,   h: 30,  xl: 48, xr: 118 },
  { id: 'CL-REG-01', y: 30,  h: 40,  xl: 44, xr: 122 },
  { id: 'CL-REG-02', y: 70,  h: 107, xl: 36, xr: 128 },
  { id: 'CL-REG-03', y: 177, h: 50,  xl: 28, xr: 122 },
  { id: 'CL-REG-04', y: 227, h: 62,  xl: 22, xr: 114 },
  { id: 'CL-REG-05', y: 289, h: 42,  xl: 15, xr: 104 },
  { id: 'CL-REG-13', y: 331, h: 26,  xl: 13, xr: 96 },
  { id: 'CL-REG-06', y: 357, h: 28,  xl: 12, xr: 98 },
  { id: 'CL-REG-07', y: 385, h: 34,  xl: 10, xr: 102 },
  { id: 'CL-REG-16', y: 419, h: 19,  xl: 8,  xr: 104 },
  { id: 'CL-REG-08', y: 438, h: 25,  xl: 6,  xr: 110 },
  { id: 'CL-REG-09', y: 463, h: 34,  xl: 4,  xr: 116 },
  { id: 'CL-REG-14', y: 497, h: 19,  xl: 2,  xr: 112 },
  { id: 'CL-REG-10', y: 516, h: 72,  xl: 0,  xr: 128 },
  { id: 'CL-REG-11', y: 588, h: 98,  xl: 0,  xr: 152 },
  { id: 'CL-REG-12', y: 686, h: 93,  xl: 0,  xr: 178 },
];

export function chileMap(regions, layerKey, selectedId) {
  const byId = new Map(regions.map((r) => [r.territory_id, r]));
  const vals = CGEO.map((g) => byId.get(g.id)?.[layerKey] ?? null);
  const known = vals.filter((v) => v !== null);
  const maxV = known.length ? Math.max(...known) : 1;
  let s = '';
  CGEO.forEach((g, i) => {
    const nxt = CGEO[i + 1] || g;
    const reg = byId.get(g.id);
    const v = vals[i];
    // Sin dato no se pinta como cero: se pinta neutro y se rotula.
    const intensity = v === null ? null : layerKey === 'exposure' ? v : (v / maxV) * 100;
    const col =
      intensity === null ? 'var(--nd)'
      : intensity >= 75 ? 'var(--cr)'
      : intensity >= 55 ? 'var(--ch)'
      : intensity >= 35 ? 'var(--cm)' : 'var(--cl)';
    const sel = g.id === selectedId;
    const pts = `${g.xl},${g.y} ${g.xr},${g.y} ${nxt.xr},${g.y + g.h} ${nxt.xl},${g.y + g.h}`;
    s += `<polygon points="${pts}" fill="${col}" stroke="${sel ? 'var(--tx)' : 'var(--bg)'}"
  stroke-width="${sel ? 2 : 1.5}" opacity="${sel ? 1 : 0.88}" data-region="${g.id}"
  style="cursor:pointer;transition:opacity .15s"><title>${reg?.name || g.id}: ${v === null ? 'sin dato' : fmt(v)}</title></polygon>`;
    s += `<text x="${(g.xl + g.xr) / 2}" y="${g.y + g.h / 2 + (g.h > 30 ? 4 : 3)}" text-anchor="middle"
  font-size="${g.h > 40 ? 9 : 8}" fill="rgba(255,255,255,.95)" font-weight="700"
  pointer-events="none" font-family="system-ui,sans-serif">${reg?.code || ''}</text>`;
  });
  return `<svg id="mapa-svg" width="185" height="782" style="flex-shrink:0;border-radius:8px">${s}</svg>`;
}

/* Grafo de relaciones en disposición radial alrededor del nodo focal.
   El borde punteado marca vínculo candidato no confirmado. */
export function networkGraph(nodes, edges, w = 720, h = 380) {
  const focus = nodes.find((n) => n.focus) || nodes[0];
  const others = nodes.filter((n) => n !== focus);
  const cx = w / 2;
  const cy = h / 2;
  const R = Math.min(w, h) * 0.36;
  const pos = new Map([[focus.node_id, { x: cx, y: cy, r: 32 }]]);
  others.forEach((n, i) => {
    const a = (i / others.length) * 2 * Math.PI - Math.PI / 2;
    pos.set(n.node_id, { x: cx + R * Math.cos(a), y: cy + R * Math.sin(a) * 0.82, r: 24 });
  });
  const srcVar = (id) => `var(--${id || 'ctx'})`;
  let s = `<rect width="${w}" height="${h}" fill="var(--s2)" rx="8"/>`;
  edges.forEach((e) => {
    const a = pos.get(e.from);
    const b = pos.get(e.to);
    if (!a || !b) return;
    s += `<line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" stroke="var(--tx2)"
  stroke-width="${e.confirmed ? 1.6 : 1.2}" opacity="${e.confirmed ? 0.5 : 0.35}"
  ${e.confirmed ? '' : 'stroke-dasharray="4,4"'}><title>${e.relation}${e.confirmed ? '' : ' (candidato)'}</title></line>`;
  });
  nodes.forEach((n) => {
    const p = pos.get(n.node_id);
    s += `<circle cx="${p.x}" cy="${p.y}" r="${p.r}" fill="${srcVar(n.source_id)}" opacity=".92"/>`;
    s += `<text x="${p.x}" y="${p.y - 2}" text-anchor="middle" font-size="8.5" fill="#fff"
  font-weight="700" pointer-events="none" font-family="system-ui,sans-serif">${n.label.slice(0, 16)}</text>`;
    s += `<text x="${p.x}" y="${p.y + 9}" text-anchor="middle" font-size="7.5" fill="rgba(255,255,255,.75)"
  pointer-events="none" font-family="system-ui,sans-serif">${(n.sublabel || '').slice(0, 20)}</text>`;
  });
  s += `<text x="${w - 10}" y="${h - 10}" text-anchor="end" font-size="8.5" fill="var(--txm)"
  font-family="system-ui,sans-serif">Línea punteada = vínculo candidato · Relación ≠ herencia de riesgo</text>`;
  return `<svg viewBox="0 0 ${w} ${h}" width="100%" height="${h}" style="display:block;border-radius:8px">${s}</svg>`;
}
