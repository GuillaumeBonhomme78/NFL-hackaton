"use strict";
/* Pocket Clock : fonctions communes (formats, couleurs, cadran, thème Plotly). DATA est injecté par viz/dashboard.py. */

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const REDUCED_MOTION = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const HAS_PLOTLY = typeof window.Plotly !== "undefined";

const RGB = { cyan: [34, 229, 255], red: [255, 59, 107], amber: [255, 194, 75], violet: [167, 139, 250],
  text: [230, 241, 255], muted: [138, 160, 189] };
const MONO = "JetBrains Mono, ui-monospace, monospace";
const FPS = 10;
const FRAME_MS = 1000 / FPS;
const MAX_CLOCK = 6;          // s : au-delà, le Pocket Clock est noté « > 6 s »
const METER_SEGMENTS = 20;
const FIELD_WIDTH = 53.3;     // yd
const RESULTS = { S: "Sack", C: "Passe complète", I: "Passe incomplète", IN: "Interception", R: "Scramble" };
const PLOT_CONFIG = { displayModeBar: false, responsive: true };

const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
const lerp = (a, b, t) => a + (b - a) * t;
const rgba = (rgb, a = 1) => `rgba(${rgb.join(",")},${a})`;
const mix = (a, b, t) => a.map((v, i) => Math.round(lerp(v, b[i], t)));
const heat = g => (g < 0.5 ? mix(RGB.cyan, RGB.amber, g / 0.5) : mix(RGB.amber, RGB.red, (g - 0.5) / 0.5));
const rankColor = t => (t < 0.5 ? mix(RGB.cyan, RGB.violet, t / 0.5) : mix(RGB.violet, RGB.red, (t - 0.5) / 0.5));

const num = (v, digits = 1) => Number(v).toFixed(digits).replace(".", ",");
const signed = (v, digits = 2) => `${v >= 0 ? "+" : "−"}${num(Math.abs(v), digits)}`;
const pct = (v, digits = 0) => `${num(v * 100, digits)} %`;
const clockLabel = v => (v >= MAX_CLOCK ? "> 6 s" : `${num(v)} s`);
const yardsLabel = v => `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v)} yd`;
const ordinal = n => `${n}<sup>${n === 1 ? "er" : "e"}</sup>`;
const escapeHtml = s => String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

/* ---------- Cadran circulaire (hero + chrono du replay) ---------- */
const SVG_NS = "http://www.w3.org/2000/svg";

function svgEl(parent, tag, attrs) {
  const node = document.createElementNS(SVG_NS, tag);
  Object.entries(attrs).forEach(([k, v]) => node.setAttribute(k, v));
  parent.append(node);
  return node;
}

function polar(value, r) {
  const angle = (value / MAX_CLOCK) * 2 * Math.PI - Math.PI / 2;
  return [100 + r * Math.cos(angle), 100 + r * Math.sin(angle)];
}

function buildDial(svg, marks = []) {
  const R = 76, C = 2 * Math.PI * R;
  svg.replaceChildren();
  svgEl(svg, "circle", { cx: 100, cy: 100, r: 95, class: "dial-orbit" });
  svgEl(svg, "circle", { cx: 100, cy: 100, r: R, class: "dial-track" });
  for (let i = 0; i < MAX_CLOCK * 4; i++) {  // un trait tous les 0,25 s, appuyé chaque seconde
    const major = i % 4 === 0;
    const [x1, y1] = polar(i / 4, R + 9), [x2, y2] = polar(i / 4, R + (major ? 17 : 13));
    svgEl(svg, "line", { x1, y1, x2, y2, class: major ? "dial-tick is-major" : "dial-tick" });
  }
  const arc = svgEl(svg, "circle", { cx: 100, cy: 100, r: R, class: "dial-arc", transform: "rotate(-90 100 100)",
    "stroke-dasharray": C.toFixed(2), "stroke-dashoffset": C.toFixed(2) });
  marks.forEach(m => {
    const [x1, y1] = polar(m.value, R - 9), [x2, y2] = polar(m.value, R + 9);
    svgEl(svg, "line", { x1, y1, x2, y2, class: `dial-mark ${m.cls}` });
    if (!m.label) return;
    const [tx, ty] = polar(m.value, R - 21);
    svgEl(svg, "text", { x: tx, y: ty, class: "dial-label", "text-anchor": "middle", "dominant-baseline": "central" })
      .textContent = m.label;
  });
  return {
    set(progress, rgb) {
      arc.setAttribute("stroke-dashoffset", (C * (1 - clamp(progress, 0, 1))).toFixed(2));
      arc.style.stroke = rgba(rgb);
      arc.style.filter = `drop-shadow(0 0 6px ${rgba(rgb, 0.8)})`;
    },
  };
}

/* ---------- Thème commun des graphiques Plotly ---------- */
function plotLayout(extra = {}) {
  const axis = { gridcolor: "rgba(140,180,255,0.08)", zeroline: false, linecolor: "rgba(140,180,255,0.2)",
    tickfont: { family: MONO, size: 11, color: rgba(RGB.muted) }, title: { font: { size: 12, color: rgba(RGB.muted) } } };
  return {
    paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)", separators: ", ", showlegend: false,
    font: { family: "system-ui, sans-serif", color: rgba(RGB.muted), size: 12 },
    margin: { l: 58, r: 18, t: 18, b: 52 },
    hoverlabel: { bgcolor: "#0a1224", bordercolor: rgba(RGB.cyan, 0.6), font: { family: MONO, color: rgba(RGB.text), size: 12 } },
    ...extra,
    xaxis: { ...axis, ...extra.xaxis, title: { ...axis.title, ...(extra.xaxis || {}).title } },
    yaxis: { ...axis, ...extra.yaxis, title: { ...axis.title, ...(extra.yaxis || {}).title } },
  };
}

function addGlow(gd) {
  $$(".scatterlayer path.js-line", gd).forEach(path => {
    if (path.style.stroke) path.style.filter = `drop-shadow(0 0 5px ${path.style.stroke})`;
  });
}

