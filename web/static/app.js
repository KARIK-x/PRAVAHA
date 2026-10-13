/* Mega Tool front end.
 *
 * No build step, no framework: plain ES5-compatible JS served from the same
 * origin as the API. Every panel that shows a number also shows the date it
 * refers to, so the UI can never present a stale figure as if it were live.
 */
"use strict";

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

const state = {
  status: null,
  charts: {},
  paneSeries: {},
  researchMeta: null,
};

/* ------------------------------------------------------------------ utils */
async function api(path, opts) {
  const res = await fetch(path, opts);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? body.error ?? detail;
      // FastAPI validation failures come back as an array of {loc, msg}.
      if (Array.isArray(detail)) {
        detail = detail
          .map((e) => (typeof e === "string" ? e : `${(e.loc || []).slice(1).join(".")} ${e.msg}`))
          .join("; ");
      }
    } catch (e) { /* body not json */ }
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json();
}

function fmtNum(v, dp = 2) {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return Number(v).toLocaleString("en-US", {
    minimumFractionDigits: dp, maximumFractionDigits: dp,
  });
}
function fmtInt(v) {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return Math.round(Number(v)).toLocaleString("en-US");
}
function fmtPct(v, dp = 2) {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  const s = Number(v).toFixed(dp);
  return `${v > 0 ? "+" : ""}${s}%`;
}
function pctClass(v) {
  if (v === null || v === undefined || Number.isNaN(v)) return "muted";
  return v > 0 ? "up" : v < 0 ? "down" : "muted";
}
/** Plain percentage (no +/- sign): for rates such as win rate or exposure. */
function pctPlain(v, dp = 2) {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return `${Number(v).toFixed(dp)}%`;
}
/** Numbers arrive already rounded to a few decimals; trim trailing zeros but
    never invent digits a value does not have. Unrenderable values show "—". */
function fmtSmart(v) {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  const n = Number(v);
  if (!Number.isFinite(n)) return "—";
  if (Number.isInteger(n)) return n.toLocaleString("en-US");
  return n.toLocaleString("en-US", { maximumFractionDigits: 4 });
}
function esc(s) {
  return String(s === null || s === undefined ? "" : s)
    .replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function table(headers, rows) {
  if (!rows.length) return `<div class="empty">Nothing to show.</div>`;
  const head = headers.map((h) => `<th>${esc(h)}</th>`).join("");
  const body = rows.map((r) => `<tr>${r.map((c) => `<td class="${c.cls || ""}">${c.html}</td>`).join("")}</tr>`).join("");
  return `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

/* ------------------------------------------------------------------ router */
function showView(name) {
  $$(".view").forEach((v) => v.classList.toggle("active", v.id === `view-${name}`));
  $$("#nav button[data-view]").forEach((b) => b.classList.toggle("active", b.dataset.view === name));
  if (name === "charts") setTimeout(() => Object.values(state.charts).forEach((c) => c.fitContent?.()), 30);
}

/* Lazy per-view work: the tabs below load their own data when shown, so a slow
   panel cannot block the boot of the rest of the terminal. */
function viewShown(name) {
  if (name === "research") {
    if (!state.researchMeta) loadResearchMeta();
    // Prefill from the chart's symbol only while the field is still empty, so a
    // symbol typed here is never overwritten.
    if (!($("#rs-symbol").value || "").trim()) {
      const current = ($("#symbol-input").value || "").trim();
      if (current) $("#rs-symbol").value = current.toUpperCase();
    }
  } else if (name === "portfolio") {
    loadPortfolio();
  } else if (name === "journal") {
    loadJournal();
  } else if (name === "pdf") {
    loadPdfSummary();
    loadPdfRecords();
  } else if (name === "floorsheet") {
    loadFsSessions();
    loadFloorSheet();
  } else if (name === "fundamentals") {
    loadFundSummary();
  }
}

/* --------------------------------------------------------------- freshness */
async function loadFreshness() {
  try {
    const s = await api("/api/status");
    state.status = s;
    const el = $("#freshness");
    const asOf = s.data_as_of || "unknown";
    el.innerHTML = `Data as of <b>${esc(asOf)}</b><br>${s.live_feed_connected ? "live feed" : "no live feed — historical dataset only"}`;
    // Staleness relative to the browser clock, shown plainly.
    if (s.data_as_of) {
      const days = (Date.now() - new Date(s.data_as_of + "T00:00:00").getTime()) / 86400000;
      if (days > 4) {
        el.classList.add("stale");
        el.innerHTML += `<br><b>stale by ${Math.floor(days)} days</b>`;
      }
    }
    $("#disclaimer").textContent = s.note || "";
  } catch (e) {
    $("#freshness").innerHTML = `<span class="down">Status unavailable: ${esc(e.message)}</span>`;
  }
}

async function loadSymbols() {
  try {
    const s = await api("/api/securities?limit=1000");
    $("#symbol-list").innerHTML = s.securities
      .map((x) => `<option value="${esc(x.symbol)}">${x.bars} bars</option>`)
      .join("");
    if (s.securities.length) $("#symbol-input").value = s.securities[0].symbol;
  } catch (e) { /* non-fatal; the input still accepts typed symbols */ }
}

/* ---------------------------------------------------------------- overview */
async function loadOverview() {
  try {
    const d = await api("/api/dashboard");
    const banner = $("#overview-banner");
    if (d.empty) {
      banner.textContent = d.note;
      return;
    }
    banner.textContent = `Figures below are computed from the latest stored trading day (${d.data_as_of}). This is not a live market feed. ${d.note}`;
    const b = d.breadth;
    $("#breadth").innerHTML = [
      ["Advancers", b.advancers, "up"],
      ["Decliners", b.decliners, "down"],
      ["Unchanged", b.unchanged, ""],
      ["No change data", b.unknown, "muted"],
    ].map(([k, v, c]) => `<div class="stat"><div class="k">${k}</div><div class="v ${c}">${fmtInt(v)}</div></div>`).join("");
    $("#breadth-hint").textContent = `Breadth uses each security's last stored percent change. Securities without change data are counted separately rather than assumed flat.`;

    $("#totals").innerHTML = [
      ["Turnover", `NPR ${fmtNum(d.total_turnover, 0)}`],
      ["Volume", fmtInt(d.total_volume)],
      ["Symbols", fmtInt(d.symbols)],
      ["As of", d.data_as_of],
    ].map(([k, v]) => `<div class="stat"><div class="k">${k}</div><div class="v">${v}</div></div>`).join("");

    const moverRows = (arr) => arr.map((r) => [
      { html: `<b>${esc(r.symbol)}</b>`, cls: "click", },
      { html: fmtNum(r.close) },
      { html: fmtPct(r.change_pct), cls: pctClass(r.change_pct) },
      { html: fmtInt(r.volume) },
      { html: fmtNum(r.turnover, 0) },
    ]);
    const hdr = ["Symbol", "Close", "Change", "Volume", "Turnover"];
    $("#gainers").innerHTML = table(hdr, moverRows(d.gainers));
    $("#losers").innerHTML = table(hdr, moverRows(d.losers));
    $("#active").innerHTML = table(
      ["Symbol", "Close", "Volume", "Turnover"],
      d.most_active.map((r) => [
        { html: `<b>${esc(r.symbol)}</b>` },
        { html: fmtNum(r.close) },
        { html: fmtInt(r.volume) },
        { html: fmtNum(r.turnover, 0) },
      ])
    );
    $$("#gainers tr.click, #losers tr.click").forEach((tr) => {
      tr.addEventListener("click", () => {
        $("#symbol-input").value = tr.cells[0].textContent.trim();
        showView("charts");
        loadChart();
      });
    });
  } catch (e) {
    $("#overview-banner").textContent = `Could not load dashboard: ${e.message}`;
  }
}

/* ------------------------------------------------------------------ charts */
function destroyCharts() {
  Object.values(state.charts).forEach((c) => { try { c.remove(); } catch (err) { /* already gone */ } });
  state.charts = {};
  state.paneSeries = {};
  ["#chart", "#rsi-pane", "#macd-pane"].forEach((id) => { $(id).innerHTML = ""; });
  if ($("#chart-note")) $("#chart-note").textContent = "";
}

function makeChart(container, height) {
  const chart = LightweightCharts.createChart(container, {
    autoSize: true,
    height,
    layout: { background: { color: "#161b22" }, textColor: "#8b949e" },
    grid: { vertLines: { color: "#20262f" }, horzLines: { color: "#20262f" } },
    rightPriceScale: { borderColor: "#2a3140" },
    timeScale: { borderColor: "#2a3140", timeVisible: false },
    crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
  });
  return chart;
}

async function loadChart() {
  const symbol = ($("#symbol-input").value || "").trim().toUpperCase();
  const errEl = $("#chart-error");
  errEl.textContent = "";
  if (!symbol) { errEl.textContent = "Enter a symbol."; return; }

  const range = $("#range").value;
  destroyCharts();

  try {
    const qs = range === "0" ? "" : `?limit=${encodeURIComponent(range)}`;
    const data = await api(`/api/bars/${encodeURIComponent(symbol)}${qs}`);
    const bars = data.bars.filter((b) => b.close !== null);

    $("#chart-meta").innerHTML =
      `<b>${esc(data.symbol)}</b> · ${data.count} bars · ${esc(data.first_date)} → <b>${esc(data.last_date)}</b>` +
      ` · source: ${data.sources.map(esc).join(", ")}` +
      ` · prices <b>${data.adjustment_status.map(esc).join("/")}</b> (not adjusted for bonus/split)`;

    if (!bars.length) { errEl.textContent = "No plottable bars (all closes missing)."; return; }

    const chart = makeChart($("#chart"), 440);
    state.charts.price = chart;

    const candle = chart.addCandlestickSeries({
      upColor: "#26a69a", downColor: "#ef5350", borderVisible: false,
      wickUpColor: "#26a69a", wickDownColor: "#ef5350",
    });
    candle.setData(bars.map((b) => ({
      time: b.time, open: b.open ?? b.close, high: b.high ?? b.close,
      low: b.low ?? b.close, close: b.close,
    })));

    if ($("#ind-vol").checked) {
      const vol = chart.addHistogramSeries({
        priceFormat: { type: "volume" }, priceScaleId: "vol",
        color: "#3a4a5f",
      });
      chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
      vol.setData(bars.map((b) => ({
        time: b.time, value: b.volume || 0,
        color: (b.close >= (b.open ?? b.close)) ? "rgba(38,166,154,.5)" : "rgba(239,83,80,.5)",
      })));
      state.paneSeries.vol = vol;
    }

    const dates = bars.map((b) => b.time);

    if ($("#ind-sma").checked) await addOverlay(chart, symbol, "sma", { period: 20 }, dates, "#f0b90b", "SMA 20");
    if ($("#ind-sma").checked) await addOverlay(chart, symbol, "sma", { period: 50 }, dates, "#4c8dff", "SMA 50");
    if ($("#ind-ema").checked) await addOverlay(chart, symbol, "ema", { period: 20 }, dates, "#e040fb", "EMA 20");
    if ($("#ind-bb").checked) {
      await addOverlay(chart, symbol, "bollinger", { period: 20, std_dev: 2 }, dates, "#8b949e", "BB mid", "middle");
      await addOverlay(chart, symbol, "bollinger", { period: 20, std_dev: 2 }, dates, "rgba(139,148,158,.6)", "BB upper", "upper");
      await addOverlay(chart, symbol, "bollinger", { period: 20, std_dev: 2 }, dates, "rgba(139,148,158,.6)", "BB lower", "lower");
    }

    if ($("#ind-rsi").checked) await addPane("rsi-pane", "rsi", symbol, {}, dates, "#4c8dff", "RSI(14)", 0, 100);
    if ($("#ind-macd").checked) {
      await addPane("macd-pane", "macd", symbol, {}, dates, "#4c8dff", "MACD");
      await addPane("macd-pane", "macd", symbol, {}, dates, "#f0b90b", "Signal", 0, 0, "signal", true);
    }
    if ($("#ind-swings").checked) await addSwings(symbol, range, candle, $("#chart-note"));

    chart.timeScale().fitContent();
    $("#export-csv").onclick = () => exportCsv(symbol, data.bars);
  } catch (e) {
    errEl.textContent = `Could not load ${symbol}: ${e.message}`;
  }
}

function indQuery(name, params) {
  const q = new URLSearchParams({ name });
  if (params && Object.keys(params).length) q.set("params", JSON.stringify(params));
  return q.toString();
}

/* Indicator responses cover the security's FULL history so the warm-up is
   computed against enough prior bars, while the price series is a window of
   it. Align by trading date, never by array index: zipping by index plotted
   2009 values onto 2026 dates (SMA ran far above price). Dates absent from
   the indicator response are dropped rather than guessed. */
function alignedSeries(resp, key, dates) {
  const vals = resp.series[key] || [];
  const byDate = new Map();
  (resp.dates || []).forEach((d, i) => byDate.set(d, vals[i]));
  return dates.map((d) => byDate.get(d) ?? null);
}

/* Swing points and market structure, drawn as chart markers.

   Two honesty rules are enforced here rather than left to the reader:
   - every marker is labelled DETECTED, never a signal or a prediction;
   - only CONFIRMED swings are drawn. An unconfirmed pivot is by definition
     future information, and plotting it would put a level on the chart that
     nobody could have known at that bar. */
async function addSwings(symbol, range, candleSeries, noteEl) {
  const qs = range === "0" ? "" : `?limit=${encodeURIComponent(range)}`;
  const d = await api(`/api/bars/${encodeURIComponent(symbol)}/structure${qs}`);
  const confirmed = (d.swings || []).filter((s) => s.confirmed);

  candleSeries.setMarkers(
    confirmed.map((s) => ({
      time: s.date,
      position: s.kind === "high" ? "aboveBar" : "belowBar",
      color: s.kind === "high" ? "#ef5350" : "#26a69a",
      shape: s.kind === "high" ? "arrowDown" : "arrowUp",
      text: s.kind === "high" ? "SH" : "SL",
    }))
  );

  if (noteEl) {
    const dropped = (d.swings || []).length - confirmed.length;
    noteEl.textContent =
      `${d.counts.swings} swings (${d.counts.swing_highs}H/${d.counts.swing_lows}L)` +
      ` · structure: ${d.trend}` +
      ` · ${d.breaks.length} break(s)` +
      (dropped ? ` · ${dropped} unconfirmed pivot(s) not drawn` : "") +
      " · DETECTED from geometry, not a validated signal";
  }
}

async function addOverlay(chart, symbol, name, params, dates, color, title, field) {  const r = await api(`/api/bars/${encodeURIComponent(symbol)}/indicator?${indQuery(name, params)}`);
  const key = field || Object.keys(r.series)[0];
  const aligned = alignedSeries(r, key, dates);
  const line = chart.addLineSeries({ color, lineWidth: 1, priceLineVisible: false, lastValueVisible: false, title });
  line.setData(
    dates
      .map((d, i) => ({ time: d, value: aligned[i] }))
      .filter((p) => p.value !== null && p.value !== undefined)
  );
}

async function addPane(paneId, name, symbol, params, dates, color, title, min, max, field, reuse) {
  let chart = state.charts[paneId];
  if (!chart || !reuse) {
    const el = $(paneId);
    if (!el) return;
    chart = makeChart(el, 170);
    state.charts[paneId] = chart;
    if (min !== undefined && max !== undefined) {
      chart.applyOptions({ rightPriceScale: { autoScale: false } });
    }
    // Align the pane's time axis with the price chart.
    const main = state.charts.price;
    if (main) {
      main.timeScale().subscribeVisibleLogicalRangeChange((r) => {
        if (r) chart.timeScale().setVisibleLogicalRange(r);
      });
      chart.timeScale().subscribeVisibleLogicalRangeChange((r) => {
        if (r) main.timeScale().setVisibleLogicalRange(r);
      });
    }
  }
  const r = await api(`/api/bars/${encodeURIComponent(symbol)}/indicator?${indQuery(name, params)}`);
  const key = field || Object.keys(r.series)[0];
  const aligned = alignedSeries(r, key, dates);
  const line = chart.addLineSeries({ color, lineWidth: 1, priceLineVisible: false, title });
  line.setData(
    dates
      .map((d, i) => ({ time: d, value: aligned[i] }))
      .filter((p) => p.value !== null && p.value !== undefined)
  );
}

function exportCsv(symbol, bars) {
  const cols = ["time", "open", "high", "low", "close", "volume", "turnover", "percent_change", "validation_status"];
  const lines = [cols.join(",")].concat(bars.map((b) => cols.map((c) => (b[c] === null || b[c] === undefined ? "" : b[c])).join(",")));
  download(`${symbol}.csv`, lines.join("\n"));
}

function download(filename, text) {
  const blob = new Blob([text], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

/* ---------------------------------------------------------------- screener */
let currentScreenTree = null;

async function loadPresets() {
  try {
    const p = await api("/api/screen/presets");
    $("#preset").innerHTML = p.presets
      .map((x) => `<option value="${esc(x.key)}">${esc(x.name)}</option>`)
      .join("");
    updatePresetDesc(p.presets);
  } catch (e) {
    $("#screen-summary").innerHTML = `<span class="down">${esc(e.message)}</span>`;
  }
}

async function updatePresetDesc(presets) {
  const list = presets || (await api("/api/screen/presets")).presets;
  const p = list.find((x) => x.key === $("#preset").value);
  if (!p) return;
  const run = async () => {
    $("#preset-desc").textContent = p.description;
    try {
      const tree = p.tree;
      currentScreenTree = tree;
      const r = await api("/api/screen", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tree }),
      });
      $("#screen-summary").innerHTML = [
        ["Condition", `<code style="font-size:12px">${esc(r.rendered)}</code>`],
        ["Evaluated", fmtInt(r.evaluated)],
        ["Eligible", fmtInt(r.eligible)],
        ["Passed", fmtInt(r.passed)],
        ["Ineligible (insufficient data)", fmtInt(r.ineligible)],
      ].map(([k, v]) => `<div class="stat"><div class="k">${k}</div><div class="v" style="font-size:14px">${v}</div></div>`).join("");

      const passed = r.results.filter((x) => x.passed);
      const inel = r.results.filter((x) => !x.eligible);
      const rows = passed.map((x) => [
        { html: `<b class="click">${esc(x.symbol)}</b>`, cls: "click" },
        { html: esc(x.last_date || "—") },
        { html: `<span class="pill pass">passed</span>` },
        { html: esc(x.reasons.join(" · ")), cls: "wrap" },
      ]).concat(inel.map((x) => [
        { html: esc(x.symbol) },
        { html: esc(x.last_date || "—") },
        { html: `<span class="pill pill-info">ineligible</span>` },
        { html: esc(x.note || x.failures.join(" · ")), cls: "wrap muted" },
      ]));
      $("#screen-results").innerHTML = table(["Symbol", "As of", "Result", "Why"], rows);
      $$("#screen-results tr.click").forEach((tr) => tr.addEventListener("click", () => {
        $("#symbol-input").value = tr.cells[0].textContent.trim();
        showView("charts");
        loadChart();
      }));
    } catch (e) {
      $("#screen-results").innerHTML = `<div class="error">${esc(e.message)}</div>`;
    }
  };
  run();
}

/* ------------------------------------------------------------------ ranking */
async function runRank() {
  const errEl = $("#rank-error");
  errEl.textContent = "";
  $("#rank-table").innerHTML = "";
  $("#rank-summary").innerHTML = "";
  try {
    const body = {
      top: parseInt($("#rank-top").value, 10) || 25,
      min_bars: parseInt($("#rank-minbars").value, 10) || 60,
    };
    const asof = $("#rank-asof").value;
    if (asof) body.as_of = asof;

    const r = await api("/api/rank", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    const excluded = (r.excluded || []).length;
    $("#rank-summary").innerHTML = [
      ["Universe", fmtInt(r.universe_size)],
      ["Ranked", fmtInt(r.ranked.length)],
      ["Insufficient data", fmtInt(excluded)],
      ["As of", r.as_of || "latest"],
      ["Factors used", fmtInt(Object.keys(r.weights).length)],
    ]
      .map(
        ([k, v]) =>
          `<div class="stat"><div class="k">${k}</div><div class="v" style="font-size:15px">${esc(v)}</div></div>`
      )
      .join("");

    if (!r.ranked.length) {
      $("#rank-table").innerHTML = `<div class="error">${esc(
        (r.notes || []).join(" · ") || "Nothing could be ranked."
      )}</div>`;
    } else {
      const rows = r.ranked.map((x) => {
        const top3 = Object.entries(x.contributions)
          .sort((a, b) => b[1] - a[1])
          .slice(0, 3)
          .map(([k, v]) => `${esc(k)} ${v.toFixed(1)}`)
          .join(" · ");
        return [
          { html: `<b>${x.rank}</b>` },
          { html: `<b class="click">${esc(x.symbol)}</b>`, cls: "click" },
          { html: esc(x.score != null ? x.score.toFixed(1) : "—") },
          { html: esc(top3), cls: "wrap muted" },
          {
            html: x.complete
              ? `<span class="pill pass">complete</span>`
              : `<span class="pill pill-info" title="${esc(x.missing.join(", "))}">gaps</span>`,
          },
        ];
      });
      $("#rank-table").innerHTML = table(
        ["#", "Symbol", "Score", "Top contributions", "Data"],
        rows
      );
      $$("#rank-table tr.click").forEach((tr) =>
        tr.addEventListener("click", () => {
          $("#symbol-input").value = tr.cells[1].textContent.trim();
          showView("charts");
          loadChart();
        })
      );
    }

    const factorRows = (r.factors || []).map((f) => [
      { html: `<code>${esc(f.key)}</code>` },
      { html: esc(f.label) },
      {
        html: f.available
          ? esc((f.weight * 100).toFixed(0) + "%")
          : `<span class="muted">n/a</span>`,
      },
      {
        html: f.available
          ? `<span class="pill pass">available</span>`
          : `<span class="pill pill-info">unavailable</span>`,
      },
      { html: esc(f.blurb || ""), cls: "wrap muted" },
    ]);
    $("#rank-factors").innerHTML = table(
      ["Factor", "Label", "Weight", "Status", "Definition"],
      factorRows
    );

    if (r.disclaimer) $("#rank-hint").textContent = r.disclaimer;
    if (r.notes && r.notes.length) {
      $("#rank-hint").textContent =
        r.disclaimer + " " + r.notes.join(" ");
    }
  } catch (e) {
    errEl.textContent = e.message;
  }
}

/* ----------------------------------------------------------- fundamentals */
async function loadFundSummary() {
  try {
    const s = await api("/api/fundamentals/summary");
    $("#fund-summary").innerHTML = [
      ["Records", fmtInt(s.total)],
      ["Symbols", fmtInt(s.symbols)],
      ["No period stated", fmtInt(s.without_period)],
      ["Verified", fmtInt((s.by_verification || {}).verified || 0)],
      ["Extracted only", fmtInt((s.by_verification || {}).extracted || 0)],
    ]
      .map(
        ([k, v]) =>
          `<div class="stat"><div class="k">${k}</div><div class="v" style="font-size:15px">${esc(v)}</div></div>`
      )
      .join("");
    $("#fund-note").textContent = s.note || "";
  } catch (e) {
    $("#fund-summary").innerHTML = `<span class="down">${esc(e.message)}</span>`;
  }
}

async function loadFundSymbol() {
  const sym = ($("#fund-symbol").value || "").trim().toUpperCase();
  const out = $("#fund-records");
  if (!sym) {
    out.innerHTML = `<div class="error">Enter a symbol first.</div>`;
    return;
  }
  try {
    const d = await api(`/api/fundamentals/${encodeURIComponent(sym)}`);
    if (!d.records.length) {
      out.innerHTML = `<div class="error">No stored fundamentals for ${esc(sym)}. Import a CSV below.</div>`;
      return;
    }
    const rows = d.records.map((r) => [
      { html: `<code>${esc(r.field)}</code>` },
      { html: `<b>${esc(String(r.value))}</b> ${esc(r.unit)}` },
      {
        html: r.period_known
          ? esc(r.period_end)
          : `<span class="pill pill-info">unknown period</span>`,
      },
      { html: esc(r.period_label || "—") },
      { html: esc(r.source) },
      {
        html:
          r.verification === "verified"
            ? `<span class="pill pass">verified</span>`
            : r.verification === "reviewed"
              ? `<span class="pill pill-info">reviewed</span>`
              : `<span class="pill pill-review">extracted</span>`,
      },
    ]);
    out.innerHTML = table(
      ["Field", "Value", "Period end", "Period label", "Source", "Verification"],
      rows
    );
  } catch (e) {
    out.innerHTML = `<div class="error">${esc(e.message)}</div>`;
  }
}

async function importFundamentals(dryRun) {
  const errEl = $("#fund-error");
  const resEl = $("#fund-result");
  errEl.textContent = "";
  resEl.textContent = "";
  const content = $("#fund-csv").value;
  if (!content.trim()) {
    errEl.textContent = "Paste or choose a CSV file first.";
    return;
  }
  try {
    const d = await api("/api/fundamentals/import", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content, dry_run: !!dryRun }),
    });
    resEl.textContent = d.dry_run
      ? `Valid: ${d.accepted} rows across ${d.symbols} symbol(s) — nothing written.`
      : `Imported ${d.written} record(s): ${d.inserted} new, ${d.updated} updated, across ${d.symbols} symbol(s).`;
    if (!d.dry_run) loadFundSummary();
  } catch (e) {
    errEl.textContent = e.message;
  }
}

/* -------------------------------------------------------------------- data */
async function loadData() {
  try {
    const s = await api("/api/status");
    const c = s.coverage;
    $("#coverage").innerHTML = [
      ["Symbols", fmtInt(c.symbols)],
      ["Bars", fmtInt(c.bars)],
      ["First bar", c.first_date || "—"],
      ["Latest bar", c.last_date || "—"],
      ["Last retrieved", (c.last_retrieved || "—").slice(0, 19)],
      ["Live feed", s.live_feed_connected ? "connected" : "not connected"],
    ].map(([k, v]) => `<div class="stat"><div class="k">${k}</div><div class="v" style="font-size:15px">${esc(v)}</div></div>`).join("");

    $("#ingest-log").innerHTML = table(
      ["Finished", "Source", "Status", "Symbols", "New rows"],
      s.recent_ingestions.map((r) => [
        { html: esc((r.finished_at || "").slice(0, 19)) },
        { html: esc(r.source) },
        { html: esc(r.status), cls: r.status === "success" ? "up" : "down" },
        { html: fmtInt(r.symbols_succeeded) },
        { html: fmtInt(r.rows_inserted) },
      ])
    );
  } catch (e) {
    $("#coverage").innerHTML = `<span class="down">${esc(e.message)}</span>`;
  }

  try {
    const s = await api("/api/sources");
    $("#sources").innerHTML = table(
      ["Source", "Access", "Auth required", "Available"],
      s.sources.map((x) => [
        { html: esc(x.label || x.source), cls: "wrap" },
        { html: esc(x.access_method || "—") },
        { html: x.requires_auth ? `<span class="pill pill-review">yes</span>` : "no" },
        { html: x.available ? `<span class="pill pill-pass">yes</span>` : `<span class="pill pill-hard">no</span>` },
      ])
    );
  } catch (e) {
    $("#sources").innerHTML = `<div class="error">${esc(e.message)}</div>`;
  }

  try {
    const q = await api("/api/quality");
    $("#quality").innerHTML = table(
      ["Symbol", "Rows", "Valid", "Review", "Invalid", "Info flags", "Dominant flags"],
      q.reports.map((r) => [
        { html: `<b>${esc(r.symbol)}</b>` },
        { html: fmtInt(r.rows_checked) },
        { html: fmtInt(r.valid) },
        { html: fmtInt(r.suspect), cls: r.suspect ? "down" : "muted" },
        { html: fmtInt(r.invalid), cls: r.invalid ? "down" : "muted" },
        { html: fmtInt(r.info_flagged), cls: "muted" },
        { html: Object.entries(r.flag_counts).slice(0, 3)
            .map(([k, v]) => `${esc(k)}×${v}`).join(", ") || "—", cls: "wrap muted" },
      ])
    );
  } catch (e) {
    $("#quality").innerHTML = `<div class="error">${esc(e.message)}</div>`;
  }
}

/* --------------------------------------------------------------- backtest */
let btStrategies = [];

function currentStrategy() {
  return btStrategies.find((s) => s.key === $("#bt-strategy").value);
}

async function loadStrategies() {
  try {
    const d = await api("/api/strategies");
    btStrategies = d.strategies;
    $("#bt-strategy").innerHTML = d.strategies
      .map((s) => `<option value="${esc(s.key)}">${esc(s.label)}</option>`)
      .join("");
    renderBtParams();
    updateBtDesc();
  } catch (e) {
    $("#bt-error").textContent = `Could not load strategies: ${e.message}`;
  }
}

function renderBtParams() {
  const s = currentStrategy();
  if (!s) { $("#bt-params").innerHTML = ""; return; }
  $("#bt-params").innerHTML = Object.entries(s.params)
    .map(([k, v]) =>
      `<label class="inline">${esc(k)} <input data-param="${esc(k)}" type="number" step="any" value="${esc(String(v))}" /></label>`)
    .join("");
}

function updateBtDesc() {
  const s = currentStrategy();
  $("#bt-desc").textContent = s ? s.description : "";
}

function collectBtParams() {
  const out = {};
  document.querySelectorAll("#bt-params input[data-param]").forEach((i) => {
    const v = parseFloat(i.value);
    if (!Number.isNaN(v)) out[i.dataset.param] = v;
  });
  return out;
}

async function runBacktest() {
  const symbol = ($("#bt-symbol").value || "").trim().toUpperCase();
  const errEl = $("#bt-error");
  errEl.textContent = "";
  if (!symbol) { errEl.textContent = "Enter a symbol."; return; }

  const btn = $("#run-backtest");
  btn.disabled = true;
  // Clear the previous run up front: a later failure must not erase results
  // that have already been rendered.
  $("#bt-metrics").innerHTML = "";
  $("#bt-equity").innerHTML = "";
  $("#bt-assumptions").innerHTML = "";
  $("#bt-warnings").innerHTML = "";
  $("#bt-trades").innerHTML = "";
  try {
    const body = {
      symbol,
      strategy: $("#bt-strategy").value,
      params: collectBtParams(),
      execution: $("#bt-execution").value,
      initial_cash: parseFloat($("#bt-cash").value) || 100000,
      // UI asks for a percentage; the API takes a fraction.
      fee_rate: (parseFloat($("#bt-fee").value) || 0) / 100,
    };
    const d = await api("/api/backtest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    renderBacktest(d);
  } catch (e) {
    errEl.textContent = `Backtest failed: ${e.message}`;
  } finally {
    btn.disabled = false;
  }
}

function renderBacktest(d) {
  const m = d.metrics;
  const cells = [
    ["Data as of", esc(d.data_as_of)],
    ["Period", `${esc(d.start)} → ${esc(d.end)}`],
    ["Final equity", fmtNum(m.final_equity)],
    ["Total return", fmtPct(m.total_return_pct)],
    ["Buy &amp; hold", fmtPct(m.benchmark_total_return_pct)],
    ["CAGR", fmtPct(m.cagr_pct)],
    ["Max drawdown", fmtPct(m.max_drawdown_pct)],
    ["Sharpe", m.sharpe === null || m.sharpe === undefined ? "—" : String(m.sharpe)],
    ["Trades", fmtInt(m.trades)],
    ["Win rate", pctPlain(m.win_rate_pct)],
    ["In market", pctPlain(m.exposure_pct)],
    ["Fees paid", fmtNum(m.fees_paid)],
  ];
  $("#bt-metrics").innerHTML = cells
    .map(([k, v]) => `<div class="stat"><div class="k">${k}</div><div class="v" style="font-size:15px">${v}</div></div>`)
    .join("");

  $("#bt-assumptions").innerHTML = (d.assumptions || [])
    .map((a) => `<li>${esc(a)}</li>`).join("") || "<li>None reported</li>";
  $("#bt-warnings").innerHTML = (d.warnings || [])
    .map((w) => `<li class="warn">${esc(w)}</li>`).join("") ||
    "<li class='muted'>No warnings.</li>";

  $("#bt-trades").innerHTML = table(
    ["Entry", "Exit", "Units", "Entry px", "Exit px", "P&L", "Return", "Bars"],
    (d.trades || []).map((t) => [
      { html: esc(t.entry_date) },
      { html: t.exit_date ? esc(t.exit_date) : "<span class='muted'>open</span>" },
      { html: fmtNum(t.units) },
      { html: fmtNum(t.entry_price) },
      { html: t.exit_price === null || t.exit_price === undefined ? "—" : fmtNum(t.exit_price) },
      { html: t.pnl === null || t.pnl === undefined ? "—" : fmtNum(t.pnl), cls: (t.pnl || 0) >= 0 ? "up" : "down" },
      { html: fmtPct(t.return_pct), cls: (t.pnl || 0) >= 0 ? "up" : "down" },
      { html: String(t.bars_held) },
    ])
  );

  const el = $("#bt-equity");
  el.innerHTML = "";
  if (!d.equity || d.equity.length < 2) {
    el.innerHTML = "<p class='hint'>Not enough points to plot an equity curve.</p>";
    return;
  }
  // Charting is best-effort: a rendering problem must not discard the numbers.
  try {
    const chart = makeChart(el, 220);
    const line = chart.addLineSeries({
      color: "#3ddc97",
      lineWidth: 2,
      priceLineVisible: false,
      title: "Equity",
    });
    line.setData(d.equity.map((p) => ({ time: p.date, value: p.equity })));
    chart.timeScale().fitContent();
  } catch (e) {
    el.innerHTML = `<p class="hint">Could not plot the equity curve: ${esc(e.message)}</p>`;
  }
}

/* --------------------------------------------------------------- research */
/* The assistant is a deterministic rules engine over stored bars, not an AI.
   Every finding carries a window and a source; both are rendered next to the
   number so no claim can travel without its provenance. */
const RESEARCH_TOPICS = ["trend", "momentum", "risk", "volume", "levels", "relative", "data"];

function prettifyKey(k) {
  return String(k).replace(/_/g, " ");
}

/** Inline rendering of a value inside a list item or table cell. */
function renderValueInline(v) {
  if (v === null || v === undefined) return "—";
  if (Array.isArray(v)) return v.map(renderValueInline).join(", ") || "—";
  if (typeof v === "object") {
    return Object.entries(v)
      .map(([k, val]) => `${esc(prettifyKey(k))}: ${renderValueInline(val)}`)
      .join(" · ");
  }
  if (typeof v === "number") return esc(fmtSmart(v));
  if (typeof v === "boolean") return v ? "yes" : "no";
  return esc(String(v));
}

/** Block rendering of a finding value: nested dicts/lists become a readable
    key/value list instead of "[object Object]". Unrenderable → "—". */
function renderValue(v) {
  if (v === null || v === undefined) return "—";
  if (Array.isArray(v)) {
    if (!v.length) return `<span class="muted">none recorded</span>`;
    return `<ul class="val-list">${v.map((x) => `<li>${renderValueInline(x)}</li>`).join("")}</ul>`;
  }
  if (typeof v === "object") {
    return `<dl class="val-dict">${Object.entries(v)
      .map(([k, val]) => `<dt>${esc(prettifyKey(k))}</dt><dd>${renderValueInline(val)}</dd>`)
      .join("")}</dl>`;
  }
  return renderValueInline(v);
}

function renderFindings(findings, topicHelp, suppressEmpty) {
  if (!findings || !findings.length)
    return suppressEmpty ? "" : `<div class="empty">No findings.</div>`;
  const groups = new Map();
  findings.forEach((f) => {
    if (!groups.has(f.topic)) groups.set(f.topic, []);
    groups.get(f.topic).push(f);
  });
  const order = RESEARCH_TOPICS.concat(
    Array.from(groups.keys()).filter((t) => !RESEARCH_TOPICS.includes(t))
  );
  return order
    .filter((t) => groups.has(t))
    .map((t) => {
      const help = topicHelp && topicHelp[t] ? `<p class="hint">${esc(topicHelp[t])}</p>` : "";
      const rows = groups.get(t).map((f) => [
        { html: `<b>${esc(f.name)}</b>` },
        { html: renderValue(f.value), cls: "wrap" },
        { html: esc(f.unit || "—"), cls: "wrap muted" },
        { html: esc(f.window || "—"), cls: "wrap muted" },
        { html: esc(f.source || "—"), cls: "wrap muted" },
      ]);
      return (
        `<h3 class="topic-head">${esc(t)}</h3>${help}` +
        table(["Finding", "Value", "Unit", "Window", "Source (citation)"], rows)
      );
    })
    .join("");
}

function renderLimitsBlock(limits) {
  if (!limits || !limits.length) return "";
  return (
    `<h3 class="topic-head">Limits of this assistant</h3><ul class="list">` +
    limits.map((x) => `<li>${esc(x)}</li>`).join("") +
    `</ul>`
  );
}

async function loadResearchMeta() {
  try {
    const d = await api("/api/research/topics");
    state.researchMeta = d;
    $("#research-banner").innerHTML =
      `<b>What this is:</b> ${esc(d.what_this_is)}<br><b>What it is not:</b> ${esc(d.what_this_is_not)}`;
  } catch (e) {
    $("#research-banner").textContent = `Could not load research topics: ${e.message}`;
  }
}

async function runResearchReport() {
  const symbol = ($("#rs-symbol").value || "").trim().toUpperCase();
  const errEl = $("#rs-error");
  errEl.textContent = "";
  if (!symbol) { errEl.textContent = "Enter a symbol."; return; }
  const btn = $("#rs-report-btn");
  btn.disabled = true;
  try {
    const d = await api(`/api/research/${encodeURIComponent(symbol)}`);
    $("#rs-report-head").textContent = d.journal_only
      ? `Journal-only — ${d.symbol}: no stored price history`
      : `Full report — ${d.symbol} as of ${d.as_of} · ${d.bars} bars since ${d.first_date} · not live`;
    $("#rs-report").innerHTML =
      renderFindings(d.findings, null, d.journal_only) +
      renderPdfFindings(d.pdf_findings);
    $("#rs-limits").innerHTML =
      (d.limits || []).map((x) => `<li>${esc(x)}</li>`).join("") ||
      "<li class='muted'>None reported.</li>";
    $("#rs-warnings").innerHTML =
      (d.warnings || []).map((x) => `<li class="warn">${esc(x)}</li>`).join("") ||
      "<li class='muted'>No warnings.</li>";
  } catch (e) {
    errEl.textContent = `Research report failed: ${e.message}`;
  } finally {
    btn.disabled = false;
  }
}

async function runResearchAsk() {
  const symbol = ($("#rs-symbol").value || "").trim().toUpperCase();
  const errEl = $("#rs-error");
  errEl.textContent = "";
  if (!symbol) { errEl.textContent = "Enter a symbol."; return; }
  const question = $("#rs-question").value || "";
  const btn = $("#rs-ask-btn");
  btn.disabled = true;
  try {
    const d = await api("/api/research/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol, question }),
    });
    renderAskAnswer(d);
  } catch (e) {
    errEl.textContent = `Ask failed: ${e.message}`;
  } finally {
    btn.disabled = false;
  }
}

function renderAskAnswer(d) {
  const el = $("#rs-answer");
  if (d.refused) {
    // A refusal is shown as the answer it is. No silent fall-back to the report.
    const offers = d.instead_offer
      ? `<h3 class="topic-head">Instead, it can answer descriptively about</h3>` +
        `<dl class="val-dict">${Object.entries(d.instead_offer)
          .map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`)
          .join("")}</dl>`
      : "";
    el.innerHTML = `<div class="banner warn"><b>Refused.</b> ${esc(d.refusal_reason)}</div>` + offers +
      renderLimitsBlock(d.limits);
    return;
  }
  el.innerHTML =
    `<p class="hint"><b>${esc(d.matched_note)}</b> · ${esc(d.symbol)} as of ${esc(d.as_of)} · ${fmtInt(d.bars)} bars</p>` +
    renderFindings(d.findings, d.topic_help, d.journal_only) +
    renderPdfFindings(d.pdf_findings) +
    renderLimitsBlock(d.limits) +
    ((d.warnings || []).length
      ? `<h3 class="topic-head">Warnings</h3><ul class="list">` +
        d.warnings.map((w) => `<li class="warn">${esc(w)}</li>`).join("") + `</ul>`
      : "");
}

function renderPdfFindings(pdfFindings) {
  if (!pdfFindings || !pdfFindings.length) return "";
  const rows = pdfFindings.map((f) => [
    { html: esc(f.field || "—") },
    { html: f.value === null || f.value === undefined ? "—" : esc(String(f.value)) },
    { html: esc(f.unit || "") },
    { html: esc(f.source || "Written Data.pdf") },
    { html: `<span class="warn">${esc(f.review_status)}</span>` },
    { html: `<span class="hint">${esc(f.note || "")}</span>` },
  ]);
  return (
    `<h3 class="topic-head">Written Data.pdf — reviewed journal records</h3>` +
    `<p class="hint">Personal handwritten records. Descriptive, not independently verified.</p>` +
    table(["Field", "Value", "Unit", "Source", "Review", "Note"], rows)
  );
}

async function runForecastCompare() {
  const symbol = ($("#rs-symbol").value || "").trim().toUpperCase();
  const errEl = $("#fc-error");
  errEl.textContent = "";
  if (!symbol) { errEl.textContent = "Enter a symbol."; return; }
  const horizon = parseInt($("#rs-horizon").value, 10);
  if (!Number.isFinite(horizon) || horizon < 1) { errEl.textContent = "Horizon must be at least 1 day."; return; }
  const btn = $("#rs-forecast-btn");
  btn.disabled = true;
  try {
    const d = await api("/api/forecast/compare", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol, horizon }),
    });
    renderForecastCompare(d);
  } catch (e) {
    errEl.textContent = `Forecast comparison failed: ${e.message}`;
  } finally {
    btn.disabled = false;
  }
}

function renderForecastCompare(d) {
  const rows = (d.ranking || []).map((r) => {
    const verdict = r.verdict || "";
    const pill = verdict.includes("NO DEMONSTRATED SKILL")
      ? `<span class="pill pill-hard">NO DEMONSTRATED SKILL</span>`
      : verdict.includes("UNDETERMINED")
        ? `<span class="pill pill-review">undetermined</span>`
        : `<span class="pill pill-info">beats naive on this one hold-out</span>`;
    return [
      { html: `<b>${esc(r.label || r.model)}</b>` },
      { html: fmtSmart(r.rmse) },
      { html: fmtSmart(r.rmse_skill_ratio) },
      { html: `${pill}<br><span class="muted">${esc(verdict)}</span>`, cls: "wrap" },
    ];
  });
  const errEntries = Object.entries(d.errors || {});
  $("#fc-results").innerHTML =
    `<p class="hint"><b>${esc(d.symbol)}</b> · hold-out: ${fmtInt(d.holdout)} day(s) · naive RMSE: ` +
    `${fmtSmart(d.naive_rmse)} · ${esc(d.note || "")}</p>` +
    table(["Model", "Hold-out RMSE", "RMSE vs naive (skill ratio)", "Verdict"], rows) +
    (errEntries.length
      ? `<p class="error">${errEntries.map(([k, v]) => `${esc(k)}: ${esc(v)}`).join("; ")}</p>`
      : "");
}

/* -------------------------------------------------------------- portfolio */
async function loadPortfolio() {
  try {
    const d = await api("/api/portfolio");
    renderPortfolio(d);
  } catch (e) {
    $("#pf-banner").textContent = `Could not load the portfolio: ${e.message}`;
  }
  try {
    const d = await api("/api/portfolio/transactions");
    renderPortfolioTransactions(d.transactions || []);
  } catch (e) {
    $("#pf-transactions").innerHTML = `<div class="error">${esc(e.message)}</div>`;
  }
}

function renderPortfolio(d) {
  const s = d.summary || {};
  $("#pf-banner").textContent =
    `Valued as of ${d.data_as_of || "no stored price for any held symbol"} — these are the latest ` +
    `STORED closes, not live quotes. ${d.note || ""}`;

  // A symbol with no stored close is left unvalued and flagged, never carried
  // at cost, so it is surfaced here as a warning rather than hidden.
  const unpriced = (d.positions || []).filter(
    (p) => p.quantity > 0 && (p.last_price === null || p.last_price === undefined)
  );
  const unpricedEl = $("#pf-unpriced");
  if (unpriced.length) {
    unpricedEl.style.display = "";
    unpricedEl.textContent =
      `${unpriced.length} position(s) have NO stored price and are left unvalued: ` +
      `${unpriced.map((p) => p.symbol).join(", ")} — unvalued cost NPR ${fmtNum(s.unvalued_cost, 0)}.`;
  } else {
    unpricedEl.style.display = "none";
  }

  $("#pf-summary").innerHTML =
    [
      ["Open positions", fmtInt(s.open_positions), ""],
      ["Market value", `NPR ${fmtNum(s.valued_market_value, 0)}`, ""],
      ["Cost (valued)", `NPR ${fmtNum(s.valued_cost, 0)}`, ""],
      ["Unrealised P&L", fmtNum(s.unrealized_pnl, 0), pctClass(s.unrealized_pnl)],
      ["Realised P&L", fmtNum(s.realized_pnl, 0), pctClass(s.realized_pnl)],
      ["Largest weight", pctPlain(s.largest_weight_pct, 1), ""],
    ]
      .map(([k, v, c]) => `<div class="stat"><div class="k">${k}</div><div class="v ${c}" style="font-size:16px">${v}</div></div>`)
      .join("") +
    (s.concentration_warning
      ? `<p class="hint warn">Concentration warning: one position is 40% or more of the valued portfolio.</p>`
      : "") +
    `<p class="hint">${esc(d.note || "")}</p>`;

  const positions = d.positions || [];
  if (!positions.length) {
    $("#pf-positions").innerHTML =
      `<div class="empty">No positions. The transaction ledger is empty — record a transaction below.</div>`;
    return;
  }
  $("#pf-positions").innerHTML = table(
    ["Symbol", "Quantity", "Avg cost", "Last price", "Market value", "Unrealised P&L", "Weight %", "Origin"],
    positions.map((p) => [
      { html: `<b>${esc(p.symbol)}</b>` },
      { html: fmtInt(p.quantity) },
      { html: fmtNum(p.avg_cost) },
      { html: fmtNum(p.last_price) },
      { html: fmtNum(p.market_value) },
      { html: fmtNum(p.unrealized_pnl), cls: pctClass(p.unrealized_pnl) },
      { html: pctPlain(p.weight_pct) },
      {
        html:
          esc(p.origin) +
          ((p.flags || []).length
            ? `<br><span class="warn">${esc(p.flags.join("; "))}</span>`
            : ""),
        cls: "wrap",
      },
    ])
  );
}

function renderPortfolioTransactions(txs) {
  if (!txs.length) {
    $("#pf-transactions").innerHTML =
      `<div class="empty">No transactions recorded. Every position above is derived from this ledger.</div>`;
    return;
  }
  $("#pf-transactions").innerHTML = table(
    ["Id", "Traded at", "Symbol", "Side", "Quantity", "Price", "Fees", "Actions"],
    txs.map((t) => [
      { html: fmtInt(t.id) },
      { html: esc((t.traded_at || "").slice(0, 19)) },
      { html: `<b>${esc(t.symbol)}</b>` },
      { html: esc(t.side), cls: t.side === "buy" ? "up" : "down" },
      { html: fmtInt(t.quantity) },
      { html: fmtNum(t.price) },
      { html: fmtNum(t.fees) },
      { html: `<button class="ghost" data-del-tx="${fmtInt(t.id)}">Delete</button>` },
    ])
  );
  $$("#pf-transactions button[data-del-tx]").forEach((b) =>
    b.addEventListener("click", () => deleteTransaction(Number(b.dataset.delTx)))
  );
}

async function addTransaction() {
  const errEl = $("#pf-tx-error");
  errEl.textContent = "";
  const body = {
    symbol: ($("#pf-tx-symbol").value || "").trim().toUpperCase(),
    side: $("#pf-tx-side").value,
    quantity: $("#pf-tx-qty").value,
    price: $("#pf-tx-price").value,
    fees: $("#pf-tx-fees").value === "" ? 0 : $("#pf-tx-fees").value,
  };
  const at = ($("#pf-tx-at").value || "").trim();
  if (at) body.traded_at = at;
  try {
    await api("/api/portfolio/transactions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    $("#pf-tx-qty").value = "";
    $("#pf-tx-price").value = "";
    loadPortfolio();
  } catch (e) {
    // Server rejections are written in plain English ("cannot sell 5 …: only 0
    // held in the ledger"); they are shown verbatim, not swallowed.
    errEl.textContent = e.message;
  }
}

async function deleteTransaction(id) {
  try {
    await api(`/api/portfolio/transactions/${id}`, { method: "DELETE" });
    $("#pf-tx-error").textContent = "";
    loadPortfolio();
  } catch (e) {
    $("#pf-tx-error").textContent = `Delete failed: ${e.message}`;
  }
}

/* ---------------------------------------------------------------- journal */
async function loadJournal() {
  try {
    const s = await api("/api/journal/stats");
    renderJournalStats(s);
  } catch (e) {
    $("#jr-stats").innerHTML = `<span class="down">${esc(e.message)}</span>`;
  }
  try {
    const j = await api("/api/journal");
    renderJournalEntries(j.entries || []);
  } catch (e) {
    $("#jr-entries").innerHTML = `<div class="error">${esc(e.message)}</div>`;
  }
}

/* ------------------------------------------------------------- PDF journal */
async function loadPdfSummary() {
  try {
    const s = await api("/api/written-pdf/summary");
    const cells = [
      { k: "records", v: s.total },
      { k: "types", v: Object.keys(s.by_type || {}).length },
      { k: "pages covered", v: s.pages_covered },
      { k: "reviewed", v: (s.by_review_status || {}).reviewed || 0 },
      { k: "unreviewed", v: (s.by_review_status || {}).unreviewed || 0 },
    ];
    $("#pdf-summary").innerHTML = cells
      .map((c) => `<div class="stat"><div class="k">${esc(c.k)}</div><div class="v">${c.v}</div></div>`)
      .join("");
    const warns = [];
    if ((s.by_review_status || {}).unreviewed) {
      warns.push("All records are unreviewed. They are descriptive, not verified market data.");
    }
    if (!s.total) {
      warns.push("No records extracted yet. Import with: megatool pdf import FILE.json");
    }
    $("#pdf-warnings").innerHTML = warns.map((w) => `<li>${esc(w)}</li>`).join("");
  } catch (e) {
    $("#pdf-summary").innerHTML = `<span class="down">${esc(e.message)}</span>`;
  }
}

async function loadPdfRecords() {
  const symbol = ($("#pdf-symbol").value || "").trim();
  const type = $("#pdf-type").value;
  const page = $("#pdf-page").value;
  const reviewed = $("#pdf-reviewed").checked;
  const params = new URLSearchParams();
  if (symbol) params.set("symbol", symbol);
  if (type) params.set("record_type", type);
  if (page) params.set("page", page);
  if (reviewed) params.set("reviewed_only", "true");
  try {
    const r = await api(`/api/written-pdf/records?${params.toString()}`);
    renderPdfRecords(r.records || []);
  } catch (e) {
    $("#pdf-records").innerHTML = `<div class="error">${esc(e.message)}</div>`;
  }
}

function renderPdfRecords(records) {
  if (!records.length) {
    $("#pdf-records").innerHTML =
      `<div class="empty">No records match. Import or review records first.</div>`;
    return;
  }
  const conf = { high: "high", medium: "medium", low: "low", uncertain: "uncertain" };
  $("#pdf-records").innerHTML = table(
    ["Page", "Type", "Symbol", "Field", "Value", "Unit", "Confidence", "Review", "Source", "Action"],
    records.slice(0, 200).map((r) => [
      { html: esc(String(r.page)) },
      { html: esc(r.record_type) },
      { html: esc(r.symbol || "—") },
      { html: esc(r.field_name || r.source_ref || "—") },
      { html: r.value === null || r.value === undefined ? "—" : esc(String(r.value)) },
      { html: esc(r.unit || "") },
      { html: esc(conf[r.confidence] || r.confidence), cls: r.confidence === "high" ? "good" : r.confidence === "uncertain" ? "bad" : "" },
      { html: esc(r.review_status), cls: r.review_status === "reviewed" ? "good" : r.review_status === "rejected" ? "bad" : "" },
      { html: esc(`p.${r.page}`) },
      {
        html:
          r.review_status === "reviewed"
            ? `<span class="hint">—</span>`
            : `<button class="ghost" data-review-id="${r.id}" data-review-status="reviewed">✓ review</button>` +
              ` <button class="ghost" data-review-id="${r.id}" data-review-status="rejected">✕ reject</button>`,
      },
    ])
  );
  $$("#pdf-records button[data-review-id]").forEach((b) =>
    b.addEventListener("click", () =>
      reviewPdfRecords([Number(b.dataset.reviewId)], b.dataset.reviewStatus)
    )
  );
}

async function reviewPdfRecords(ids, status) {
  try {
    await api("/api/written-pdf/review", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids, status }),
    });
    loadPdfSummary();
    loadPdfRecords();
  } catch (e) {
    $("#pdf-records").insertAdjacentHTML(
      "afterbegin",
      `<div class="error">${esc(e.message)}</div>`
    );
  }
}

/* ------------------------------------------------------------ floor sheet */
async function loadFsSessions() {
  try {
    const d = await api("/api/floorsheet/sessions");
    const sel = $("#fs-session");
    const keep = sel.value;
    sel.innerHTML =
      `<option value="">All sessions</option>` +
      (d.sessions || [])
        .map(
          (s) =>
            `<option value="${esc(s.traded_at)}">${esc(s.traded_at)} · ${fmtInt(s.prints)} prints</option>`
        )
        .join("");
    if (keep) sel.value = keep;
  } catch (e) {
    /* an empty session list is a normal state, not an error to surface */
  }
}

async function loadFloorSheet() {
  const params = new URLSearchParams();
  const session = $("#fs-session").value;
  const symbol = ($("#fs-symbol").value || "").trim();
  if (session) params.set("traded_at", session);
  if (symbol) params.set("symbol", symbol.toUpperCase());
  params.set("top", $("#fs-top").value || "10");
  try {
    const d = await api(`/api/floorsheet/summary?${params}`);
    renderFloorSheet(d);
  } catch (e) {
    $("#fs-totals").innerHTML = `<div class="error">${esc(e.message)}</div>`;
  }
}

function renderFloorSheet(d) {
  const t = d.totals || {};
  const f = d.filter || {};
  $("#fs-totals").innerHTML =
    [
      ["Prints", fmtInt(t.trades)],
      ["Symbols", fmtInt(t.symbols)],
      ["Sessions", fmtInt(t.sessions)],
      ["Quantity", fmtSmart(t.quantity)],
      ["Amount", fmtSmart(t.amount)],
    ]
      .map(([k, v]) => `<div class="stat"><div class="k">${k}</div><div class="v" style="font-size:16px">${v}</div></div>`)
      .join("") +
    `<p class="hint">Scope: ${esc(f.traded_at || "all sessions")} · ${esc(f.symbol || "all symbols")}</p>`;

  $("#fs-warnings").innerHTML =
    (d.warnings || []).map((w) => `<li class="warn">${esc(w)}</li>`).join("") ||
    "<li class='muted'>No warnings.</li>";

  const money = (v) => (v === null || v === undefined ? "—" : fmtSmart(v));
  const pct = (v) => (v === null || v === undefined ? "—" : `${Number(v).toFixed(2)}%`);
  const empty = `<div class="empty">Nothing imported yet. Paste a session's floor sheet above.</div>`;

  const counterparty = (rows, key) =>
    rows && rows.length
      ? table(
          ["Broker", "Quantity", "Amount", "% of session qty", "% of session amount"],
          rows.map((r) => [
            { html: `<b>${esc(r[key])}</b>` },
            { html: fmtInt(r.quantity) },
            { html: money(r.amount) },
            { html: pct(r.share_of_quantity_pct) },
            { html: pct(r.share_of_amount_pct) },
          ])
        )
      : empty;

  $("#fs-buyers").innerHTML = counterparty(d.top_buyers, "buyer");
  $("#fs-sellers").innerHTML = counterparty(d.top_sellers, "seller");

  $("#fs-symbols").innerHTML =
    d.top_symbols && d.top_symbols.length
      ? table(
          ["Symbol", "Quantity", "Amount", "Prints", "Distinct buyers", "Distinct sellers"],
          d.top_symbols.map((r) => [
            { html: `<b>${esc(r.symbol)}</b>` },
            { html: fmtInt(r.quantity) },
            { html: money(r.amount) },
            { html: fmtInt(r.prints) },
            { html: fmtInt(r.distinct_buyers) },
            { html: fmtInt(r.distinct_sellers) },
          ])
        )
      : empty;

  $("#fs-pairs").innerHTML =
    d.top_counterparties && d.top_counterparties.length
      ? table(
          ["Buyer", "Seller", "Prints", "Quantity", "Amount"],
          d.top_counterparties.map((r) => [
            { html: esc(r.buyer) },
            { html: esc(r.seller) },
            { html: fmtInt(r.prints) },
            { html: fmtInt(r.quantity) },
            { html: money(r.amount) },
          ])
        )
      : empty;

  const c = d.concentration || {};
  const hhi = (v) => (v === null || v === undefined ? "—" : Number(v).toFixed(0));
  $("#fs-concentration").innerHTML =
    table(
      ["Side", "Unique broker codes", "HHI", "Reading"],
      [
        [
          { html: "<b>Buyers</b>" },
          { html: fmtInt(c.unique_buyers) },
          { html: hhi(c.buyer_hhi) },
          { html: hhiReading(c.buyer_hhi), cls: "wrap" },
        ],
        [
          { html: "<b>Sellers</b>" },
          { html: fmtInt(c.unique_sellers) },
          { html: hhi(c.seller_hhi) },
          { html: hhiReading(c.seller_hhi), cls: "wrap" },
        ],
      ]
    ) + `<p class="hint">${esc(c.interpretation || "")}</p>`;

  $("#fs-sessions").innerHTML =
    d.sessions && d.sessions.length
      ? table(
          ["Session", "Prints", "Amount"],
          d.sessions.map((r) => [
            { html: `<b>${esc(r.traded_at)}</b>` },
            { html: fmtInt(r.prints) },
            { html: money(r.amount) },
          ])
        )
      : `<div class="empty">No sessions imported.</div>`;

  $("#fs-imports").innerHTML =
    d.recent_imports && d.recent_imports.length
      ? table(
          ["Source", "Session", "Rows imported", "When"],
          d.recent_imports.map((r) => [
            { html: esc(r.source || "—") },
            { html: esc(r.traded_at) },
            {
              html: `${fmtInt(r.rows_imported)} / ${fmtInt(r.rows_total)} (skipped ${fmtInt(r.rows_skipped)})`,
            },
            { html: esc(r.imported_at || "—"), cls: "wrap muted" },
          ])
        )
      : `<div class="empty">No imports recorded.</div>`;
}

function hhiReading(hhi) {
  if (hhi === null || hhi === undefined) return "—";
  const v = Number(hhi);
  if (v >= 2500) return `<span class="bad">concentrated</span>`;
  if (v >= 1500) return `moderate`;
  return `dispersed`;
}

async function importFloorSheet() {
  const text = $("#fs-import-text").value;
  const traded_at = $("#fs-import-date").value;
  const msg = $("#fs-import-msg");
  msg.textContent = "";
  if (!text.trim()) { msg.textContent = "Paste the CSV text first."; return; }
  if (!traded_at) { msg.textContent = "Pick the trading date this sheet belongs to."; return; }
  try {
    const d = await api("/api/floorsheet/import", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text,
        traded_at,
        source: ($("#fs-import-source").value || "").trim() || "manual import",
      }),
    });
    msg.textContent = `Imported ${d.rows_imported} of ${d.rows_total} rows (${d.rows_skipped} skipped).`;
    $("#fs-import-text").value = "";
    loadFsSessions();
    loadFloorSheet();
  } catch (e) {
    msg.textContent = e.message;
  }
}

function renderJournalStats(s) {
  // With no closed trades the API returns nulls, not zeroes: "—" is shown so a
  // missing statistic is never presented as a real 0%.
  $("#jr-stats").innerHTML =
    [
      ["Entries", fmtInt(s.entries)],
      ["Open", fmtInt(s.open)],
      ["Closed", fmtInt(s.closed)],
      ["Win rate", s.win_rate_pct === null ? "—" : pctPlain(s.win_rate_pct)],
      ["Avg R", s.avg_r === null ? "—" : fmtSmart(s.avg_r)],
      ["Plan adherence", s.plan_adherence_pct === null ? "—" : pctPlain(s.plan_adherence_pct)],
    ]
      .map(([k, v]) => `<div class="stat"><div class="k">${k}</div><div class="v" style="font-size:16px">${v}</div></div>`)
      .join("") +
    `<p class="hint">${esc(s.note || "")}</p>`;
  $("#jr-warnings").innerHTML =
    (s.warnings || []).map((w) => `<li class="warn">${esc(w)}</li>`).join("") ||
    "<li class='muted'>No warnings.</li>";

  const by = s.by_strategy || [];
  $("#jr-by-strategy").innerHTML = by.length
    ? table(
        ["Strategy", "Closed", "Wins", "Win rate", "Avg R", "Graded"],
        by.map((b) => [
          { html: `<b>${esc(b.strategy)}</b>`, cls: "wrap" },
          { html: fmtInt(b.closed) },
          { html: fmtInt(b.wins) },
          { html: b.win_rate_pct === null ? "—" : pctPlain(b.win_rate_pct) },
          { html: b.avg_r === null ? "—" : fmtSmart(b.avg_r) },
          { html: fmtInt(b.graded_r) },
        ])
      )
    : `<div class="empty">No closed entries yet, so there is nothing to break down by strategy.</div>`;
}

function renderJournalEntries(entries) {
  if (!entries.length) {
    $("#jr-entries").innerHTML =
      `<div class="empty">No journal entries yet. Record the plan first (thesis, entry, target, ` +
      `invalidation) and fill in the outcome when the trade is closed.</div>`;
    return;
  }
  $("#jr-entries").innerHTML = table(
    ["Id", "Symbol", "Strategy", "Entry", "Target", "Invalidation", "Confidence", "Followed plan", "Opened", "Exit", "Closed", "Actions"],
    entries.map((e) => {
      const closed = Boolean(e.closed_at);
      const actions =
        (closed ? `<button class="ghost" data-grade="${fmtInt(e.id)}">Grade</button> ` : `<span class="muted">open</span> `) +
        `<button class="ghost" data-del-entry="${fmtInt(e.id)}">Delete</button>`;
      return [
        { html: fmtInt(e.id) },
        { html: `<b>${esc(e.symbol || "—")}</b>` },
        { html: esc(e.strategy || "—"), cls: "wrap" },
        { html: fmtNum(e.entry_price) },
        { html: fmtNum(e.planned_target) },
        { html: fmtNum(e.planned_invalidation) },
        { html: esc(e.confidence || "—") },
        { html: e.followed_plan === null || e.followed_plan === undefined ? "—" : e.followed_plan ? "yes" : "no" },
        { html: esc((e.opened_at || "").slice(0, 19) || "—") },
        { html: fmtNum(e.exit_price) },
        { html: esc((e.closed_at || "").slice(0, 19) || "—") },
        { html: actions, cls: "wrap" },
      ];
    })
  );
  $$("#jr-entries button[data-grade]").forEach((b) =>
    b.addEventListener("click", () => gradeEntry(Number(b.dataset.grade)))
  );
  $$("#jr-entries button[data-del-entry]").forEach((b) =>
    b.addEventListener("click", () => deleteJournalEntry(Number(b.dataset.delEntry)))
  );
}

async function addJournalEntry() {
  const errEl = $("#jr-form-error");
  errEl.textContent = "";
  const notes = ($("#jr-notes").value || "").trim();
  const body = {
    symbol: ($("#jr-symbol").value || "").trim().toUpperCase(),
    strategy: ($("#jr-strategy").value || "").trim() || null,
    thesis: ($("#jr-thesis").value || "").trim() || null,
    entry_price: ($("#jr-entry").value || "").trim() || null,
    planned_target: ($("#jr-target").value || "").trim() || null,
    planned_invalidation: ($("#jr-invalidation").value || "").trim() || null,
    confidence: $("#jr-confidence").value || null,
    followed_plan: $("#jr-followed").value === "" ? null : Number($("#jr-followed").value),
    opened_at: ($("#jr-opened").value || "").trim() || null,
    exit_price: ($("#jr-exit").value || "").trim() || null,
    closed_at: ($("#jr-closed").value || "").trim() || null,
    // The journal persists free text under `outcome_notes`; the API accepts any
    // key, so `notes` (the human-facing name) is sent alongside it and nothing
    // typed into the field is silently dropped.
    outcome_notes: notes || null,
    notes: notes || null,
  };
  try {
    await api("/api/journal", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    ["#jr-thesis", "#jr-notes", "#jr-entry", "#jr-target", "#jr-invalidation",
     "#jr-opened", "#jr-exit", "#jr-closed"].forEach((sel) => { $(sel).value = ""; });
    loadJournal();
  } catch (e) {
    errEl.textContent = e.message;
  }
}

async function deleteJournalEntry(id) {
  try {
    await api(`/api/journal/${id}`, { method: "DELETE" });
    $("#jr-form-error").textContent = "";
    loadJournal();
  } catch (e) {
    $("#jr-form-error").textContent = `Delete failed: ${e.message}`;
  }
}

async function gradeEntry(id) {
  const el = $("#jr-grade");
  el.innerHTML = `<div class="empty">Grading entry ${id}…</div>`;
  try {
    const g = await api(`/api/journal/${id}/grade`);
    el.innerHTML =
      `<p class="hint">Entry ${fmtInt(id)} · ${esc(g.result)}</p>` +
      `<div class="stat-row">` +
      [
        ["R multiple", fmtSmart(g.r_multiple)],
        ["Planned R", fmtSmart(g.planned_r)],
        ["Actual vs plan %", fmtSmart(g.planned_vs_actual_pct)],
      ]
        .map(([k, v]) => `<div class="stat"><div class="k">${k}</div><div class="v" style="font-size:16px">${v}</div></div>`)
        .join("") +
      `</div><p class="hint">${esc(g.note || "")}</p>`;
  } catch (e) {
    // The API explains exactly what is missing ("cannot be graded: …").
    el.innerHTML = `<div class="error">${esc(e.message)}</div>`;
  }
}

async function runPlanner() {
  const errEl = $("#plan-error");
  errEl.textContent = "";
  const body = {
    entry: parseFloat($("#plan-entry").value),
    stop: parseFloat($("#plan-stop").value),
    target: parseFloat($("#plan-target").value),
  };
  if ([body.entry, body.stop, body.target].some((v) => Number.isNaN(v))) {
    errEl.textContent = "Entry, stop and target are all required numbers.";
    return;
  }
  const capital = ($("#plan-capital").value || "").trim();
  const risk = ($("#plan-risk").value || "").trim();
  if (capital !== "" || risk !== "") {
    if (capital === "" || risk === "") {
      errEl.textContent = "Capital and risk % must be supplied together (or both left empty).";
      return;
    }
    body.capital = parseFloat(capital);
    body.risk_pct = parseFloat(risk);
  }
  try {
    const d = await api("/api/planning", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    renderPlanner(d);
  } catch (e) {
    errEl.textContent = e.message;
    $("#plan-result").innerHTML = "";
  }
}

function renderPlanner(d) {
  const p = d.plan || {};
  const cells = [
    ["Risk per share", fmtNum(p.risk_per_share)],
    ["Reward per share", fmtNum(p.reward_per_share)],
    ["Risk : reward", fmtSmart(p.risk_reward)],
    ["Risk % of entry", pctPlain(p.risk_pct_of_entry)],
    ["Invalidation %", pctPlain(p.invalidation_pct)],
    ["Target %", pctPlain(p.target_pct)],
  ];
  if (d.sizing) {
    cells.push(
      ["Units", fmtInt(d.sizing.units)],
      ["Cash used", `NPR ${fmtNum(d.sizing.cash_used, 0)}`],
      ["Actual risk", `NPR ${fmtNum(d.sizing.actual_risk, 0)}`],
      ["Actual risk %", pctPlain(d.sizing.actual_risk_pct)]
    );
  }
  $("#plan-result").innerHTML =
    `<div class="stat-row">` +
    cells.map(([k, v]) => `<div class="stat"><div class="k">${k}</div><div class="v" style="font-size:15px">${v}</div></div>`).join("") +
    `</div><p class="hint">${esc(d.note || "")}</p>`;
}

/* -------------------------------------------------------------------- boot */
function boot() {
  $$("#nav button[data-view]").forEach((b) =>
    b.addEventListener("click", () => { showView(b.dataset.view); viewShown(b.dataset.view); })
  );
  $("#load-chart").addEventListener("click", loadChart);
  $("#symbol-input").addEventListener("keydown", (e) => { if (e.key === "Enter") loadChart(); });
  $("#run-screen").addEventListener("click", () => updatePresetDesc());
  $("#preset").addEventListener("change", () => updatePresetDesc());
  $("#run-rank").addEventListener("click", runRank);
  $("#rank-asof").addEventListener("keydown", (e) => { if (e.key === "Enter") runRank(); });
  $("#fund-load").addEventListener("click", loadFundSymbol);
  $("#fund-symbol").addEventListener("keydown", (e) => { if (e.key === "Enter") loadFundSymbol(); });
  $("#fund-dryrun").addEventListener("click", () => importFundamentals(true));
  $("#fund-import").addEventListener("click", () => importFundamentals(false));
  $("#fund-file").addEventListener("change", (e) => {
    const file = e.target.files && e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => { $("#fund-csv").value = String(reader.result || ""); };
    reader.onerror = () => { $("#fund-error").textContent = "Could not read that file."; };
    reader.readAsText(file);
  });
  $("#export-screen").addEventListener("click", () => {
    if (!currentScreenTree) return;
    const url = `/api/screen/export.csv?tree=${encodeURIComponent(JSON.stringify(currentScreenTree))}`;
    window.location.href = url;
  });
  $("#bt-strategy").addEventListener("change", () => { renderBtParams(); updateBtDesc(); });
  $("#run-backtest").addEventListener("click", runBacktest);
  $("#bt-symbol").addEventListener("keydown", (e) => { if (e.key === "Enter") runBacktest(); });

  $("#rs-report-btn").addEventListener("click", runResearchReport);
  $("#rs-ask-btn").addEventListener("click", runResearchAsk);
  $("#rs-forecast-btn").addEventListener("click", runForecastCompare);
  $("#rs-symbol").addEventListener("keydown", (e) => { if (e.key === "Enter") runResearchReport(); });
  $("#rs-question").addEventListener("keydown", (e) => { if (e.key === "Enter") runResearchAsk(); });

  $("#pf-tx-add").addEventListener("click", addTransaction);
  $("#pf-tx-qty").addEventListener("keydown", (e) => { if (e.key === "Enter") addTransaction(); });
  $("#pf-tx-price").addEventListener("keydown", (e) => { if (e.key === "Enter") addTransaction(); });

  $("#jr-add").addEventListener("click", addJournalEntry);
  $("#plan-run").addEventListener("click", runPlanner);

  $("#pdf-load").addEventListener("click", () => { loadPdfSummary(); loadPdfRecords(); });
  $("#pdf-symbol").addEventListener("keydown", (e) => { if (e.key === "Enter") loadPdfRecords(); });
  $("#pdf-page").addEventListener("keydown", (e) => { if (e.key === "Enter") loadPdfRecords(); });
  $("#pdf-reviewed").addEventListener("change", loadPdfRecords);
  $("#pdf-type").addEventListener("change", loadPdfRecords);
  $("#fs-load").addEventListener("click", loadFloorSheet);
  $("#fs-session").addEventListener("change", loadFloorSheet);
  $("#fs-top").addEventListener("change", loadFloorSheet);
  $("#fs-symbol").addEventListener("keydown", (e) => { if (e.key === "Enter") loadFloorSheet(); });
  $("#fs-import").addEventListener("click", importFloorSheet);

  loadFreshness();
  loadSymbols();
  loadOverview();
  loadPresets();
  loadData();
  loadStrategies();
  loadResearchMeta();
}

document.addEventListener("DOMContentLoaded", boot);
