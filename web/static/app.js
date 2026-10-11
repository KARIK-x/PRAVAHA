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

async function addOverlay(chart, symbol, name, params, dates, color, title, field) {
  const r = await api(`/api/bars/${encodeURIComponent(symbol)}/indicator?${indQuery(name, params)}`);
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

/* -------------------------------------------------------------------- boot */
function boot() {
  $$("#nav button[data-view]").forEach((b) => b.addEventListener("click", () => showView(b.dataset.view)));
  $("#load-chart").addEventListener("click", loadChart);
  $("#symbol-input").addEventListener("keydown", (e) => { if (e.key === "Enter") loadChart(); });
  $("#run-screen").addEventListener("click", () => updatePresetDesc());
  $("#preset").addEventListener("change", () => updatePresetDesc());
  $("#export-screen").addEventListener("click", () => {
    if (!currentScreenTree) return;
    const url = `/api/screen/export.csv?tree=${encodeURIComponent(JSON.stringify(currentScreenTree))}`;
    window.location.href = url;
  });
  $("#bt-strategy").addEventListener("change", () => { renderBtParams(); updateBtDesc(); });
  $("#run-backtest").addEventListener("click", runBacktest);
  $("#bt-symbol").addEventListener("keydown", (e) => { if (e.key === "Enter") runBacktest(); });

  loadFreshness();
  loadSymbols();
  loadOverview();
  loadPresets();
  loadData();
  loadStrategies();
}

document.addEventListener("DOMContentLoaded", boot);
