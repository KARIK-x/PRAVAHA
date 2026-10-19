/* =====================================================================
   viz.js — dependency-free SVG visualisation primitives for PRAVAHA.

   Everything here renders from values handed to it by a caller that has
   already fetched them from a real API endpoint. This module never
   invents, samples, interpolates or "demo-fills" data: an empty or
   missing series renders an explicit empty state, never a fake bar.

   Design constraints (see FINAL_REFERENCE_IMPLEMENTATION_AND_REMAINING_GAPS_REPORT.md):
     * No new third-party dependency — hand-rolled SVG, theme-aware via the
       app's existing CSS custom properties.
     * Accessible: each chart is role="img" with an aria-label summary, and
       every mark carries a <title> so keyboard/screen-reader users and
       hover users get the same numbers.
     * Interactive where it matters: line charts expose a hover readout.
     * Responsive: charts measure their host and re-render on resize.

   Public API (all functions return the <svg> element, or null on no data):
     VIZ.line(host, spec)      multi-series time/sequence line or area chart
     VIZ.bars(host, spec)      vertical or horizontal bar chart (± colouring)
     VIZ.donut(host, spec)     donut / pie with legend
     VIZ.gauge(host, spec)     semicircular dial with coloured zones
     VIZ.sparkline(host, spec) tiny inline trend line
     VIZ.scatter(host, spec)   x/y scatter with optional size encoding
     VIZ.empty(host, text)     explicit empty state (never a fabricated chart)
   ===================================================================== */
(function () {
  "use strict";

  const NS = "http://www.w3.org/2000/svg";

  /* Colours are read from the PRAVAHA design tokens at runtime so the charts
     follow the same single source of truth as the stylesheet. The literals are
     offline/pre-CSS fallbacks only. */
  function cssVar(name, fallback) {
    try {
      const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
      return v || fallback;
    } catch (e) { return fallback; }
  }
  const TOKEN = {
    bg:     cssVar("--pravaha-panel", "#102722"),
    bg3:    cssVar("--pravaha-panel-3", "#16332C"),
    line:   cssVar("--pravaha-border", "#24453C"),
    txt:    cssVar("--pravaha-white", "#F5F8F7"),
    muted:  cssVar("--pravaha-muted", "#9DB4AE"),
    accent: cssVar("--pravaha-emerald", "#00D69A"),
    up:     cssVar("--pravaha-up", "#1FC98A"),
    down:   cssVar("--pravaha-down", "#FF6B78"),
    warn:   cssVar("--pravaha-caution", "#E9C46A"),
    info:   cssVar("--pravaha-cyan", "#00D9E8"),
  };

  const PALETTE = [
    "#00D9E8", "#00D69A", "#E9C46A", "#A8FFD9", "#FF6B78",
    "#9DB4AE", "#1FC98A", "#326B5C", "#0AE3A6", "#F5F8F7",
  ];

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function isNum(v) { return typeof v === "number" && Number.isFinite(v); }

  function fmt(v, digits) {
    if (!isNum(v)) return "—";
    const d = typeof digits === "number" ? digits : 2;
    return v.toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d });
  }

  function mk(tag, attrs) {
    const e = document.createElementNS(NS, tag);
    if (attrs) for (const k in attrs) if (attrs[k] != null) e.setAttribute(k, attrs[k]);
    return e;
  }

  function hostSize(host, defaultW, height) {
    const w = Math.max(240, Math.round((host && host.clientWidth) || defaultW || 640));
    return { w, h: height };
  }

  function clear(host) {
    if (!host) return;
    host.innerHTML = "";
    const tip = host.querySelector && host.querySelector(":scope > .viz-tip");
    if (tip) tip.remove();
  }

  /* An explicit, honest empty state. */
  function empty(host, text) {
    if (!host) return null;
    clear(host);
    host.classList.add("viz-host");
    const d = document.createElement("div");
    d.className = "viz-empty empty";
    d.textContent = text || "No data available for this view.";
    host.appendChild(d);
    return null;
  }

  /* Schedule a re-render on resize without leaking observers. */
  function attachResize(host, fn) {
    if (!host || host.__vizResize) return;
    const handler = () => {
      if (!host.__vizSpec) return;
      clearTimeout(host.__vizT);
      host.__vizT = setTimeout(() => {
        try { host.__vizFn(host, host.__vizSpec); } catch (e) { /* keep the last good render */ }
      }, 120);
    };
    if (typeof ResizeObserver !== "undefined") {
      host.__vizResize = new ResizeObserver(handler);
      host.__vizResize.observe(host);
    } else {
      host.__vizResize = handler;
      window.addEventListener("resize", handler);
    }
  }

  function registerSpec(host, fn, spec) {
    host.__vizFn = fn;
    host.__vizSpec = spec;
    attachResize(host, fn);
  }

  function ensureHost(host) {
    if (!host) return false;
    host.classList.add("viz-host");
    return true;
  }

  function tooltip(host) {
    let tip = host.querySelector(":scope > .viz-tip");
    if (!tip) {
      tip = document.createElement("div");
      tip.className = "viz-tip";
      tip.hidden = true;
      host.appendChild(tip);
    }
    return tip;
  }

  function legend(host, series) {
    const box = document.createElement("div");
    box.className = "viz-legend";
    box.innerHTML = series.map((s) => `<span class="viz-key"><i style="background:${esc(s.color || TOKEN.accent)}"></i>${esc(s.name || "")}</span>`).join("");
    host.appendChild(box);
    return box;
  }

  function niceTicks(min, max, count) {
    if (!isNum(min) || !isNum(max)) return [];
    if (min === max) { min -= 1; max += 1; }
    const span = max - min;
    const step0 = span / Math.max(1, count);
    const mag = Math.pow(10, Math.floor(Math.log10(step0)));
    const norm = step0 / mag;
    const step = (norm >= 5 ? 5 : norm >= 2 ? 2 : 1) * mag;
    const start = Math.ceil(min / step) * step;
    const out = [];
    for (let v = start; v <= max + step * 0.001; v += step) out.push(Number(v.toFixed(10)));
    return out;
  }

  function axesGroup(opts) {
    const { w, h, min, max, yFormat, yLabel } = opts;
    const g = mk("g");
    const ticks = niceTicks(min, max, 4);
    const yOf = opts.yOf;
    ticks.forEach((t) => {
      const y = yOf(t);
      g.appendChild(mk("line", { x1: 0, y1: y, x2: w, y2: y, stroke: TOKEN.line, "stroke-width": 1, "stroke-dasharray": "2 4", opacity: 0.7 }));
      const tx = mk("text", { x: 2, y: y - 3, fill: TOKEN.muted, "font-size": 10 });
      tx.textContent = (yFormat ? yFormat(t) : fmt(t, 2));
      g.appendChild(tx);
    });
    if (yLabel) {
      const tl = mk("text", { x: 2, y: 10, fill: TOKEN.muted, "font-size": 10, "font-weight": "600" });
      tl.textContent = yLabel;
      g.appendChild(tl);
    }
    return g;
  }

  /* ------------------------------------------------------------------ line */
  function line(host, spec) {
    if (!ensureHost(host)) return null;
    const labels = spec.labels || [];
    const series = (spec.series || []).filter((s) => s && Array.isArray(s.values));
    const have = series.some((s) => s.values.some(isNum));
    if (!labels.length || !series.length || !have) return empty(host, spec.emptyText);
    const { w, h } = hostSize(host, spec.width, spec.height || 220);
    const padTop = 12, padBottom = spec.xLabels === false ? 8 : 20, padLeft = spec.padLeft || 44, padRight = 10;
    const plotW = Math.max(10, w - padLeft - padRight);
    const plotH = Math.max(20, h - padTop - padBottom);
    let min = spec.yMin, max = spec.yMax;
    if (!isNum(min) || !isNum(max)) {
      const all = [];
      series.forEach((s) => s.values.forEach((v) => { if (isNum(v)) all.push(v); }));
      if (spec.zeroLine) all.push(0);
      min = Math.min.apply(null, all); max = Math.max.apply(null, all);
      if (min === max) { min -= 1; max += 1; }
      const padv = (max - min) * 0.08;
      min -= padv; max += padv;
    }
    const xOf = (i) => padLeft + (labels.length <= 1 ? plotW / 2 : (i / (labels.length - 1)) * plotW);
    const yOf = (v) => padTop + (1 - (v - min) / (max - min)) * plotH;

    clear(host);
    const svg = mk("svg", { width: "100%", height: h, viewBox: `0 0 ${w} ${h}`, role: "img", "aria-label": spec.ariaLabel || "line chart" });
    const g = mk("g", { transform: `translate(${padLeft},${padTop})` });

    const grid = mk("g");
    grid.appendChild(axesGroup({ w: plotW, h: plotH, min, max, yFormat: spec.yFormat, yLabel: spec.yLabel, yOf: (t) => (1 - (t - min) / (max - min)) * plotH }));
    g.appendChild(grid);

    if (spec.zeroLine && min < 0 && max > 0) {
      g.appendChild(mk("line", { x1: 0, y1: yOf(0) - padTop, x2: plotW, y2: yOf(0) - padTop, stroke: TOKEN.muted, "stroke-width": 1 }));
    }
    (spec.bands || []).forEach((b) => {
      const y1 = yOf(b.to) - padTop, y2 = yOf(b.from) - padTop;
      g.appendChild(mk("rect", { x: 0, y: Math.min(y1, y2), width: plotW, height: Math.abs(y2 - y1), fill: b.color || TOKEN.warn, opacity: b.opacity == null ? 0.08 : b.opacity }));
    });

    series.forEach((s, si) => {
      const color = s.color || PALETTE[si % PALETTE.length];
      let d = "", started = false;
      s.values.forEach((v, i) => {
        if (!isNum(v)) { started = false; return; }
        const x = xOf(i) - padLeft, y = yOf(v) - padTop;
        d += (started ? " L" : " M") + x.toFixed(1) + " " + y.toFixed(1);
        started = true;
      });
      if (s.area) {
        const firstIdx = s.values.findIndex(isNum);
        const lastIdx = (() => { for (let i = s.values.length - 1; i >= 0; i--) if (isNum(s.values[i])) return i; return -1; })();
        if (firstIdx >= 0) {
          const base = spec.zeroLine ? Math.max(min, 0) : min;
          const areaD = d + ` L${(xOf(lastIdx) - padLeft).toFixed(1)} ${(yOf(base) - padTop).toFixed(1)} L${(xOf(firstIdx) - padLeft).toFixed(1)} ${(yOf(base) - padTop).toFixed(1)} Z`;
          g.appendChild(mk("path", { d: areaD, fill: color, opacity: 0.14, stroke: "none" }));
        }
      }
      g.appendChild(mk("path", { d, fill: "none", stroke: color, "stroke-width": s.width || 1.6, "stroke-linejoin": "round" }));
    });

    if (spec.xLabels !== false && labels.length) {
      const want = Math.min(labels.length, Math.max(2, Math.floor(plotW / 90)));
      for (let k = 0; k < want; k++) {
        const i = Math.round((k / (want - 1 || 1)) * (labels.length - 1));
        const t = mk("text", { x: xOf(i) - padLeft, y: plotH + 14, fill: TOKEN.muted, "font-size": 10, "text-anchor": k === 0 ? "start" : k === want - 1 ? "end" : "middle" });
        t.textContent = String(labels[i]);
        g.appendChild(t);
      }
    }
    svg.appendChild(g);
    host.appendChild(svg);

    if (spec.interactive !== false) {
      const tip = tooltip(host);
      const overlay = mk("rect", { x: padLeft, y: padTop, width: plotW, height: plotH, fill: "transparent", style: "cursor:crosshair" });
      const cross = mk("line", { x1: 0, y1: padTop, x2: 0, y2: padTop + plotH, stroke: TOKEN.txt, "stroke-width": 1, opacity: 0.5, "pointer-events": "none" });
      svg.appendChild(overlay); svg.appendChild(cross);
      const onMove = (ev) => {
        const rect = svg.getBoundingClientRect();
        const scale = rect.width ? w / rect.width : 1;
        const px = (ev.clientX - rect.left) * scale;
        const rel = Math.max(0, Math.min(1, (px - padLeft) / plotW));
        const i = Math.round(rel * (labels.length - 1));
        cross.setAttribute("x1", xOf(i)); cross.setAttribute("x2", xOf(i));
        const rows = series.map((s) => {
          const v = s.values[i];
          return `<div><i style="background:${esc(s.color || TOKEN.accent)}"></i>${esc(s.name || "")}: <b>${esc(spec.yFormat ? spec.yFormat(v) : fmt(v, 2))}</b></div>`;
        }).join("");
        tip.innerHTML = `<div class="viz-tip-t">${esc(labels[i])}</div>${rows}`;
        tip.hidden = false;
        const rectHost = host.getBoundingClientRect();
        let left = (xOf(i) / scale) + 8;
        if (left > rectHost.width - 150) left = (xOf(i) / scale) - 150;
        tip.style.left = Math.max(0, left) + "px";
        tip.style.top = Math.max(0, (ev.clientY - rectHost.top) - 10) + "px";
      };
      overlay.addEventListener("mousemove", onMove);
      overlay.addEventListener("mouseleave", () => { tip.hidden = true; });
      svg.addEventListener("touchmove", (ev) => { if (ev.touches && ev.touches[0]) onMove(ev.touches[0]); }, { passive: true });
    }
    if (spec.legend) legend(host, series);
    registerSpec(host, line, spec);
    return svg;
  }

  /* ------------------------------------------------------------------ bars */
  function bars(host, spec) {
    if (!ensureHost(host)) return null;
    const items = (spec.items || []).filter((it) => it && isNum(it.value));
    if (!items.length) return empty(host, spec.emptyText);
    const horiz = spec.orientation === "h";
    const h = spec.height || (horiz ? Math.max(60, items.length * 22 + 24) : 200);
    const { w } = hostSize(host, spec.width, h);
    clear(host);

    if (horiz) {
      const labelW = spec.labelWidth || 110;
      const padRight = 52, padTop = 4, padBottom = 4, gap = 6;
      const plotW = Math.max(20, w - labelW - padRight);
      const rowH = (h - padTop - padBottom) / items.length;
      const maxAbs = Math.max.apply(null, items.map((it) => Math.abs(it.value)).concat([0.000001]));
      const svg = mk("svg", { width: "100%", height: h, viewBox: `0 0 ${w} ${h}`, role: "img", "aria-label": spec.ariaLabel || "bar chart" });
      items.forEach((it, i) => {
        const col = it.color || (spec.signed ? (it.value >= 0 ? TOKEN.up : TOKEN.down) : PALETTE[i % PALETTE.length]);
        const bw = Math.max(2, (Math.abs(it.value) / maxAbs) * plotW);
        const x = labelW;
        const y = padTop + i * rowH + gap / 2;
        const bh = Math.max(6, rowH - gap);
        const rect = mk("rect", { x, y, width: bw, height: bh, rx: 3, fill: col, opacity: 0.9 });
        rect.appendChild(mk("title", {})).textContent = `${it.label}: ${spec.valueFormat ? spec.valueFormat(it.value) : fmt(it.value, 2)}`;
        svg.appendChild(rect);
        const lbl = mk("text", { x: labelW - 8, y: y + bh / 2 + 4, fill: TOKEN.txt, "font-size": 11, "text-anchor": "end" });
        lbl.textContent = it.label;
        lbl.appendChild(mk("title", {})).textContent = it.label;
        svg.appendChild(lbl);
        const val = mk("text", { x: x + bw + 6, y: y + bh / 2 + 4, fill: TOKEN.muted, "font-size": 11 });
        val.textContent = spec.valueFormat ? spec.valueFormat(it.value) : fmt(it.value, 2);
        svg.appendChild(val);
        if (it.href) { rect.style.cursor = "pointer"; rect.addEventListener("click", () => it.href()); }
      });
      host.appendChild(svg);
      registerSpec(host, bars, spec);
      return svg;
    }

    // vertical
    const padTop = 14, padBottom = 30, padLeft = 42, padRight = 8;
    const plotW = Math.max(10, w - padLeft - padRight);
    const plotH = Math.max(20, h - padTop - padBottom);
    let vals = items.map((it) => it.value);
    if (spec.zeroLine) vals = vals.concat([0]);
    let min = Math.min.apply(null, vals), max = Math.max.apply(null, vals);
    if (min === max) { min -= 1; max += 1; }
    const span = max - min; min -= span * 0.05; max += span * 0.05;
    const yOf = (v) => padTop + (1 - (v - min) / (max - min)) * plotH;
    const slot = plotW / items.length;
    const bw = Math.max(3, Math.min(spec.maxBarWidth || 44, slot * 0.72));
    const svg = mk("svg", { width: "100%", height: h, viewBox: `0 0 ${w} ${h}`, role: "img", "aria-label": spec.ariaLabel || "bar chart" });

    // grid + y labels
    niceTicks(min, max, 4).forEach((t) => {
      const y = yOf(t);
      svg.appendChild(mk("line", { x1: padLeft, y1: y, x2: w - padRight, y2: y, stroke: TOKEN.line, "stroke-dasharray": "2 4", opacity: 0.6 }));
      const tx = mk("text", { x: padLeft - 6, y: y + 3, fill: TOKEN.muted, "font-size": 10, "text-anchor": "end" });
      tx.textContent = spec.yFormat ? spec.yFormat(t) : fmt(t, 1);
      svg.appendChild(tx);
    });
    if (min < 0 && max > 0) {
      svg.appendChild(mk("line", { x1: padLeft, y1: yOf(0), x2: w - padRight, y2: yOf(0), stroke: TOKEN.muted, "stroke-width": 1 }));
    }
    if (isNum(spec.meanLine)) {
      const y = yOf(spec.meanLine);
      const ml = mk("line", { x1: padLeft, y1: y, x2: w - padRight, y2: y, stroke: TOKEN.warn, "stroke-width": 1.4, "stroke-dasharray": "5 4" });
      ml.appendChild(mk("title", {})).textContent = `mean ${spec.yFormat ? spec.yFormat(spec.meanLine) : fmt(spec.meanLine, 2)}`;
      svg.appendChild(ml);
    }
    const base = yOf(Math.max(min, 0));
    items.forEach((it, i) => {
      const col = it.color || (spec.signed ? (it.value >= 0 ? TOKEN.up : TOKEN.down) : TOKEN.accent);
      const cx = padLeft + slot * i + slot / 2;
      const y = yOf(it.value);
      const yTop = Math.min(y, base), bh = Math.max(1.5, Math.abs(base - y));
      const rect = mk("rect", { x: cx - bw / 2, y: yTop, width: bw, height: bh, rx: 3, fill: col, opacity: 0.92 });
      rect.appendChild(mk("title", {})).textContent = `${it.label}: ${spec.valueFormat ? spec.valueFormat(it.value) : fmt(it.value, 2)}`;
      svg.appendChild(rect);
      if (spec.showValues !== false) {
        const vl = mk("text", { x: cx, y: it.value >= 0 ? yTop - 4 : yTop + bh + 11, fill: TOKEN.muted, "font-size": 10, "text-anchor": "middle" });
        vl.textContent = spec.valueFormat ? spec.valueFormat(it.value) : fmt(it.value, 1);
        svg.appendChild(vl);
      }
      const lbl = mk("text", { x: cx, y: h - 12, fill: TOKEN.muted, "font-size": 10, "text-anchor": "middle" });
      lbl.textContent = it.shortLabel || it.label;
      lbl.appendChild(mk("title", {})).textContent = it.label;
      svg.appendChild(lbl);
    });
    host.appendChild(svg);
    if (spec.legend) legend(host, items.map((it, i) => ({ name: it.label, color: it.color || TOKEN.accent })));
    registerSpec(host, bars, spec);
    return svg;
  }

  /* ----------------------------------------------------------------- donut */
  function donut(host, spec) {
    if (!ensureHost(host)) return null;
    const slices = (spec.slices || []).filter((s) => isNum(s.value) && s.value > 0);
    if (!slices.length) return empty(host, spec.emptyText);
    const h = spec.height || 220;
    const { w } = hostSize(host, spec.width, h);
    const size = Math.min(h, spec.maxSize || 220, w * 0.6);
    const r = size / 2 - 6;
    const ir = r * (spec.innerRatio == null ? 0.58 : spec.innerRatio);
    const total = slices.reduce((a, s) => a + s.value, 0);
    const cx = size / 2, cy = h / 2;
    clear(host);
    const svg = mk("svg", { width: size, height: h, viewBox: `0 0 ${size} ${h}`, role: "img", "aria-label": spec.ariaLabel || "donut chart", style: "flex:0 0 auto" });
    let a0 = -Math.PI / 2;
    slices.forEach((s, i) => {
      const frac = s.value / total;
      const a1 = a0 + frac * Math.PI * 2;
      const large = frac > 0.5 ? 1 : 0;
      const p = (rad, ang) => [cx + rad * Math.cos(ang), cy + rad * Math.sin(ang)];
      const [x0, y0] = p(r, a0), [x1, y1] = p(r, a1), [x2, y2] = p(ir, a1), [x3, y3] = p(ir, a0);
      const d = `M${x0.toFixed(1)} ${y0.toFixed(1)} A${r} ${r} 0 ${large} 1 ${x1.toFixed(1)} ${y1.toFixed(1)} L${x2.toFixed(1)} ${y2.toFixed(1)} A${ir} ${ir} 0 ${large} 0 ${x3.toFixed(1)} ${y3.toFixed(1)} Z`;
      const path = mk("path", { d, fill: s.color || PALETTE[i % PALETTE.length], opacity: 0.92 });
      path.appendChild(mk("title", {})).textContent = `${s.label}: ${spec.valueFormat ? spec.valueFormat(s.value) : fmt(s.value, 0)} (${(frac * 100).toFixed(1)}%)`;
      svg.appendChild(path);
      a0 = a1;
    });
    if (spec.centerLabel || spec.centerSub) {
      const t1 = mk("text", { x: cx, y: cy - (spec.centerSub ? 2 : -4), fill: TOKEN.txt, "font-size": 16, "font-weight": "700", "text-anchor": "middle" });
      t1.textContent = spec.centerLabel || "";
      svg.appendChild(t1);
      if (spec.centerSub) {
        const t2 = mk("text", { x: cx, y: cy + 14, fill: TOKEN.muted, "font-size": 10, "text-anchor": "middle" });
        t2.textContent = spec.centerSub;
        svg.appendChild(t2);
      }
    }
    const wrap = document.createElement("div");
    wrap.className = "viz-donut-wrap";
    wrap.appendChild(svg);
    const lg = document.createElement("div");
    lg.className = "viz-legend viz-legend-col";
    lg.innerHTML = slices.map((s, i) => {
      const pct = (s.value / total) * 100;
      return `<span class="viz-key" title="${esc(s.label)}"><i style="background:${esc(s.color || PALETTE[i % PALETTE.length])}"></i>${esc(s.label)} <b>${pct.toFixed(1)}%</b></span>`;
    }).join("");
    wrap.appendChild(lg);
    host.appendChild(wrap);
    registerSpec(host, donut, spec);
    return svg;
  }

  /* ----------------------------------------------------------------- gauge */
  function gauge(host, spec) {
    if (!ensureHost(host)) return null;
    const value = spec.value;
    if (!isNum(value)) return empty(host, spec.emptyText || "No value to display.");
    const h = spec.height || 170;
    const { w } = hostSize(host, spec.width, h);
    const size = Math.min(w, spec.maxSize || 320);
    const cx = size / 2, cy = h - 26, r = Math.min(size / 2 - 10, h - 46);
    const min = isNum(spec.min) ? spec.min : 0, max = isNum(spec.max) ? spec.max : 100;
    const zones = spec.zones || [
      { from: min, to: max * 0.25, color: TOKEN.down, label: "Weak" },
      { from: max * 0.25, to: max * 0.5, color: TOKEN.warn, label: "Soft" },
      { from: max * 0.5, to: max * 0.75, color: TOKEN.up, label: "Firm" },
      { from: max * 0.75, to: max, color: TOKEN.up, label: "Strong" },
    ];
    const ang = (v) => Math.PI - ((v - min) / (max - min)) * Math.PI;
    const pt = (rad, a) => [cx + rad * Math.cos(a), cy - rad * Math.sin(a)];
    const arc = (from, to, rad) => {
      const [x0, y0] = pt(rad, ang(from)), [x1, y1] = pt(rad, ang(to));
      return `M${x0.toFixed(1)} ${y0.toFixed(1)} A${rad} ${rad} 0 0 1 ${x1.toFixed(1)} ${y1.toFixed(1)}`;
    };
    clear(host);
    const svg = mk("svg", { width: size, height: h, viewBox: `0 0 ${size} ${h}`, role: "img", "aria-label": spec.ariaLabel || "gauge" });
    zones.forEach((z) => {
      const path = mk("path", { d: arc(z.from, z.to, r - 12), fill: "none", stroke: z.color, "stroke-width": 14, "stroke-linecap": "butt", opacity: 0.85 });
      path.appendChild(mk("title", {})).textContent = `${z.label || ""} ${z.from.toFixed(0)}–${z.to.toFixed(0)}`;
      svg.appendChild(path);
    });
    const a = ang(Math.max(min, Math.min(max, value)));
    const [nx, ny] = pt(r - 22, a);
    svg.appendChild(mk("line", { x1: cx, y1: cy, x2: nx, y2: ny, stroke: TOKEN.txt, "stroke-width": 2.4, "stroke-linecap": "round" }));
    svg.appendChild(mk("circle", { cx, cy, r: 4, fill: TOKEN.txt }));
    const vt = mk("text", { x: cx, y: cy - 14, fill: TOKEN.txt, "font-size": 22, "font-weight": "700", "text-anchor": "middle" });
    vt.textContent = spec.valueFormat ? spec.valueFormat(value) : fmt(value, 0);
    svg.appendChild(vt);
    const lbl = mk("text", { x: cx, y: cy + 14, fill: TOKEN.muted, "font-size": 11, "text-anchor": "middle" });
    lbl.textContent = spec.label || "";
    svg.appendChild(lbl);
    const lmin = mk("text", { x: 6, y: cy + 14, fill: TOKEN.muted, "font-size": 10 }); lmin.textContent = String(min); svg.appendChild(lmin);
    const lmax = mk("text", { x: size - 6, y: cy + 14, fill: TOKEN.muted, "font-size": 10, "text-anchor": "end" }); lmax.textContent = String(max); svg.appendChild(lmax);
    if (spec.sub) {
      const sub = mk("text", { x: cx, y: h - 6, fill: TOKEN.muted, "font-size": 10, "text-anchor": "middle" });
      sub.textContent = spec.sub;
      svg.appendChild(sub);
    }
    host.appendChild(svg);
    registerSpec(host, gauge, spec);
    return svg;
  }

  /* -------------------------------------------------------------- sparkline */
  function sparkline(host, spec) {
    const values = (spec.values || []).filter(isNum);
    if (values.length < 2) { return empty(host, spec.emptyText || "—"); }
    if (!ensureHost(host)) return null;
    const h = spec.height || 26;
    const { w } = hostSize(host, spec.width || 90, h);
    clear(host);
    const min = Math.min.apply(null, values), max = Math.max.apply(null, values);
    const xOf = (i) => (i / (values.length - 1)) * (w - 2) + 1;
    const yOf = (v) => 2 + (1 - (v - min) / ((max - min) || 1)) * (h - 4);
    const d = values.map((v, i) => (i ? "L" : "M") + xOf(i).toFixed(1) + " " + yOf(v).toFixed(1)).join(" ");
    const up = values[values.length - 1] >= values[0];
    const col = spec.color || (up ? TOKEN.up : TOKEN.down);
    const svg = mk("svg", { width: "100%", height: h, viewBox: `0 0 ${w} ${h}`, role: "img", "aria-label": spec.ariaLabel || "sparkline", preserveAspectRatio: "none" });
    const path = mk("path", { d, fill: "none", stroke: col, "stroke-width": 1.4, "vector-effect": "non-scaling-stroke" });
    path.appendChild(mk("title", {})).textContent = `${values.length} points · ${fmt(values[0], 2)} → ${fmt(values[values.length - 1], 2)}`;
    svg.appendChild(path);
    host.appendChild(svg);
    registerSpec(host, sparkline, spec);
    return svg;
  }

  /* ---------------------------------------------------------------- scatter */
  function scatter(host, spec) {
    if (!ensureHost(host)) return null;
    const pts = (spec.points || []).filter((p) => isNum(p.x) && isNum(p.y));
    if (!pts.length) return empty(host, spec.emptyText);
    const h = spec.height || 320;
    const { w } = hostSize(host, spec.width, h);
    const padTop = 12, padBottom = 34, padLeft = 48, padRight = 14;
    const plotW = Math.max(10, w - padLeft - padRight), plotH = Math.max(10, h - padTop - padBottom);
    const xs = pts.map((p) => p.x), ys = pts.map((p) => p.y);
    let xmin = Math.min.apply(null, xs), xmax = Math.max.apply(null, xs);
    let ymin = Math.min.apply(null, ys), ymax = Math.max.apply(null, ys);
    if (spec.xMin != null) xmin = spec.xMin; if (spec.xMax != null) xmax = spec.xMax;
    if (spec.yMin != null) ymin = spec.yMin; if (spec.yMax != null) ymax = spec.yMax;
    if (xmin === xmax) xmax = xmin + 1;
    if (ymin === ymax) ymax = ymin + 1;
    const padx = (xmax - xmin) * 0.06, pady = (ymax - ymin) * 0.08;
    xmin -= padx; xmax += padx; ymin -= pady; ymax += pady;
    const X = (v) => padLeft + ((v - xmin) / (xmax - xmin)) * plotW;
    const Y = (v) => padTop + (1 - (v - ymin) / (ymax - ymin)) * plotH;
    const rsize = (p) => {
      if (!spec.sizeBy) return spec.r || 4;
      const s = p.r || 0;
      return Math.max(3, Math.min(spec.maxR || 16, 3 + Math.sqrt(Math.max(0, s)) / (spec.sizeScale || 1)));
    };
    clear(host);
    const svg = mk("svg", { width: "100%", height: h, viewBox: `0 0 ${w} ${h}`, role: "img", "aria-label": spec.ariaLabel || "scatter plot" });
    niceTicks(ymin, ymax, 5).forEach((t) => {
      svg.appendChild(mk("line", { x1: padLeft, y1: Y(t), x2: w - padRight, y2: Y(t), stroke: TOKEN.line, "stroke-dasharray": "2 4", opacity: 0.6 }));
      const tx = mk("text", { x: padLeft - 6, y: Y(t) + 3, fill: TOKEN.muted, "font-size": 10, "text-anchor": "end" });
      tx.textContent = spec.yFormat ? spec.yFormat(t) : fmt(t, 1); svg.appendChild(tx);
    });
    if (ymin < 0 && ymax > 0) svg.appendChild(mk("line", { x1: padLeft, y1: Y(0), x2: w - padRight, y2: Y(0), stroke: TOKEN.muted, "stroke-width": 1 }));
    niceTicks(xmin, xmax, 5).forEach((t) => {
      const tx = mk("text", { x: X(t), y: h - 18, fill: TOKEN.muted, "font-size": 10, "text-anchor": "middle" });
      tx.textContent = spec.xFormat ? spec.xFormat(t) : fmt(t, 1); svg.appendChild(tx);
    });
    pts.forEach((p) => {
      const c = mk("circle", { cx: X(p.x), cy: Y(p.y), r: rsize(p), fill: p.color || spec.color || TOKEN.accent, opacity: 0.7, stroke: TOKEN.bg, "stroke-width": 0.6 });
      c.appendChild(mk("title", {})).textContent = p.label ? p.label : `x=${fmt(p.x, 2)}, y=${fmt(p.y, 2)}`;
      if (spec.onPick) { c.style.cursor = "pointer"; c.addEventListener("click", () => spec.onPick(p)); }
      svg.appendChild(c);
    });
    if (spec.xLabel) { const t = mk("text", { x: padLeft + plotW / 2, y: h - 4, fill: TOKEN.muted, "font-size": 10, "text-anchor": "middle" }); t.textContent = spec.xLabel; svg.appendChild(t); }
    if (spec.yLabel) { const t = mk("text", { x: 12, y: 10, fill: TOKEN.muted, "font-size": 10 }); t.textContent = spec.yLabel; svg.appendChild(t); }
    host.appendChild(svg);
    registerSpec(host, scatter, spec);
    return svg;
  }

  window.VIZ = { line, bars, donut, gauge, sparkline, scatter, empty, TOKEN, PALETTE };
})();
