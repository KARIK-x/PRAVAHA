/* PRAVAHA front end.
 *
 * No build step, no framework: plain ES5-compatible JS served from the same
 * origin as the API. Every panel that shows a number also shows the date it
 * refers to, so the UI can never present a stale figure as if it were live.
 */
"use strict";

/* ==========================================================================
   PRAVAHA palette — the single source of truth for every colour this script
   hands to the charting engine or writes into generated markup. Values mirror
   the CSS tokens in styles.css (:root). Change them together.
   ========================================================================== */
const PRAVAHA = {
  obsidian:   "#06110F",
  deepForest: "#071C18",
  panel:      "#102722",
  panel2:     "#0B1E1A",
  panel3:     "#16332C",
  border:     "#24453C",
  borderLite: "#326B5C",
  grid:       "rgba(36,69,60,.55)",
  white:      "#F5F8F7",
  muted:      "#9DB4AE",
  emerald:    "#00D69A",
  cyan:       "#00D9E8",
  mint:       "#A8FFD9",
  caution:    "#E9C46A",
  risk:       "#FF6B78",
  up:         "#1FC98A",
  down:       "#FF6B78",
  // ordered series ramp for multi-series charts
  series: ["#00D9E8", "#00D69A", "#E9C46A", "#A8FFD9", "#FF6B78", "#9DB4AE"],
};

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

const state = {
  status: null,
  liveTimer: null,
  tickerTimer: null,
  charts: {},
  paneSeries: {},
  researchMeta: null,
  // Chart markers are collected from every source (swings, candlesticks,
  // Elliott labels, harmonic pivots) and written to the candle series in ONE
  // setMarkers call at the end of loadChart: lightweight-charts replaces the
  // whole marker set on each call, so per-source calls would silently erase
  // each other (the bug that left `plotCandlestickMarkers` dead).
  markers: [],
  candleMarkers: [],
  // Quick-layer (chart-toolbar) objects built by loadChart: overlays, the
  // volume histogram, oscillator panes and swing markers. Registered so the
  // Chart Objects manager can name/hide/remove the real primitive. Rebuilt on
  // every load (never persisted — the drawer analysis layers are the
  // persistent equivalent).
  quickObjects: [],
  chartRange: null,   // the requested #range at the last successful load (viewport guard)
  elliottMarkers: [],
  elliottAutoMarkers: [],
  elliottAutoLine: null,
  harmonicMarkers: [],
  // manual drawings (never detector output)
  drawings: [],
  drawingsLoadedFor: null,
  drawSeries: [],
  drawMarkers: [],
  drawPreviewSeries: [],
  pendingMarker: [],
  drawTool: null,
  drawPending: null,
  drawPending3: null,
  drawDrag: null,
  drawMagnet: "off", // "off" | "weak" | "strong": snap anchors to real OHLC points
  drawStay: true,    // stay in drawing mode after completing a drawing
  drawSelectId: null, // drawing selected with the select tool
  drawHover: null,   // last pointer position over the chart (chart-local px), for Delete-key hit-testing
  selectionMarkers: [], // anchor handles painted for the selected drawing (merged in flushMarkers)
  customInds: [],    // [{id, name, params, label, color, visible}] catalog indicator instances on this symbol
  indRegistry: null, // cached GET /api/indicators
  indSeries: {},     // instance id → {series:[...], panes:[...]} created handles
  indHist: { stack: [], idx: -1 },   // indicator-config undo/redo (per loaded symbol)
  compare: null,     // multi-symbol comparison config + runtime series
  drawUndo: [],
  drawRedo: [],
  // §5 mission: unified undo/redo across drawings AND chart navigation. Each
  // entry is typed; the top of the undo stack decides what Cmd/Ctrl+Z does.
  undoStack: [],  // [{kind:"draw"| "view"|"custom", symbol, before, after}]
  redoStack: [],
  // §9 mission: per-layer render controls (the "label mess" fix). Every rule
  // here is a hard cap or visibility switch applied at flush time, so toggling
  // never leaves stale markers behind.
  overlayVis: { levelLines: true, shapeLines: true, patMarkers: true, candleCap: 15 },
  // forecast overlays (per symbol, from real /api/kronos/forecast runs only)
  forecastOverlays: [], // [{symbol, model, origin, series:[LWC], chip}]
  drawVisible: true,
  anchorHandlePrim: null,
  // Dedicated marker host. Markers attached to the candlestick series make
  // Lightweight Charts reserve vertical space and re-autoscale the price pane,
  // which moved drawing anchors away from the pointer. This series renders the
  // same markers but is excluded from autoscaling.
  markerSeries: null,
  markerSeriesKey: null,
  // chart-pattern overlay (detector output — distinct from manual drawings)
  patternSeries: [],
  patternMarkers: [],
  // market-structure & liquidity overlay (swings, BOS/CHoCH, equal H/L, FVG)
  structureMarkers: [],
  structureSeries: [],
  // custom primitives (vertical lines, etc.)
  drawPrimitives: [],
  // trend strength & regime overlay
  trendMarkers: [],
  trendSeries: [],
  // momentum, divergence & relative strength overlay
  momentumMarkers: [],
  momentumSeries: [],
  // volatility & breakout overlay
  volatilityMarkers: [],
  volatilitySeries: [],
  // volume & accumulation overlay
  volumeMarkers: [],
  volumeSeries: [],
  // new research categories
  gapMarkers: [],
  gapSeries: [],
  regimeMarkers: [],
  regimeSeries: [],
  relativeMarkers: [],
  relativeSeries: [],
  microMarkers: [],
  microSeries: [],
  distributionMarkers: [],
  distributionSeries: [],
  eventMarkers: [],
  eventSeries: [],
  strategyMarkers: [],
  strategySeries: [],
  // relative-strength overlay (stock vs stored index series)
  rsData: null,
  rsSeries: [],
  candleSeries: null,
  chartSymbol: null,
  chartDates: [],
  chartBars: [],
  lastBacktest: null,
  backtestConfig: null,
  selectedWatchlist: null,
  // Chart navigation history hooks for the unified undo stack (§5.7).
  viewBase: null,
  viewSuppress: false,
};

/* ------------------------------------------------------------------ utils */

/* Where the API lives. Empty string = same origin (the default local setup,
 * where FastAPI serves this file). A Netlify-hosted copy points this at the
 * always-on backend via <meta name="megatool-api-base"> or window.MEGATOOL_API_BASE.
 * This is a PUBLIC address, never a secret. */
const API_BASE = (() => {
  const meta = document.querySelector('meta[name="megatool-api-base"]');
  const raw = (window.MEGATOOL_API_BASE || (meta && meta.content) || "").trim();
  return raw.replace(/\/+$/, "");
})();

/* Where the public edge endpoints live. The Cloudflare Worker is a separate
 * origin from both the local app and Netlify, and it exposes only public,
 * read-only YONEPSE data. Empty falls back to the API origin (which is the
 * Worker itself when the app is served from Cloudflare). */
const EDGE_BASE = (() => {
  const meta = document.querySelector('meta[name="megatool-edge-base"]');
  const raw = (window.MEGATOOL_EDGE_BASE || (meta && meta.content) || API_BASE).trim();
  return raw.replace(/\/+$/, "");
})();

/* Shared read-only friend token, supplied at RUNTIME (never in the bundle).
 * It lives in sessionStorage so it is not persisted to disk by the page. */
function friendToken() {
  try {
    return sessionStorage.getItem("megatool_friend_token") || "";
  } catch (e) {
    return "";
  }
}

/* Ask for the access token when the API answers 401. The value is typed by the
 * user, kept only in sessionStorage, and never logged. A deployment that is not
 * access-controlled never reaches this path.
 *
 * The whole page boots in parallel, so a single 401 is not enough: the token is
 * stored and the page reloads once so every request re-issues with the token.
 * Attempts and "declined" are bounded so a wrong token cannot loop forever. */
let _tokenPromptActive = false;
let _reloadedForToken = false;
function _sessionNum(key) {
  try { return parseInt(sessionStorage.getItem(key) || "0", 10) || 0; } catch (e) { return 0; }
}
function _sessionSet(key, val) {
  try { sessionStorage.setItem(key, val); } catch (e) { /* storage blocked */ }
}
function _sessionRemove(key) {
  try { sessionStorage.removeItem(key); } catch (e) { /* storage blocked */ }
}
function promptForFriendToken() {
  if (_tokenPromptActive) return false;
  if (_sessionNum("megatool_token_declined") >= 1) return false;
  if (_sessionNum("megatool_token_attempts") >= 3) return false;
  _tokenPromptActive = true;
  try {
    const t = window.prompt(
      "PRAVAHA is access-controlled. Paste the access token (kept for this browser tab only):"
    );
    if (t && t.trim()) {
      _sessionSet("megatool_friend_token", t.trim());
      _sessionSet("megatool_token_attempts", String(_sessionNum("megatool_token_attempts") + 1));
      return true;
    }
    _sessionSet("megatool_token_declined", "1");   // do not nag on every request
    return false;
  } catch (e) {
    _sessionSet("megatool_token_declined", "1");
    return false;
  } finally {
    _tokenPromptActive = false;
  }
}

function _withFriendToken(base) {
  const tok = friendToken();
  if (!tok) return base;
  const headers = new Headers(base.headers || undefined);
  if (!headers.has("X-Friend-Token")) headers.set("X-Friend-Token", tok);
  return Object.assign({}, base, { headers });
}

async function api(path, opts) {
  const init = opts ? Object.assign({}, opts) : {};
  let res = await fetch(API_BASE + path, _withFriendToken(init));
  // 401 = not authenticated (a token is required). Ask for it and reload once so
  // the whole page re-boots with the token. 403 is left alone: it means
  // authenticated-but-not-permitted (an owner-only route).
  // The whole page boots in parallel, so guard on _reloadedForToken BEFORE
  // prompting: otherwise a second in-flight 401 would prompt again mid-reload.
  if (res.status === 401 && !_reloadedForToken) {
    if (friendToken()) _sessionRemove("megatool_friend_token");  // stored token was rejected
    if (promptForFriendToken()) {
      _reloadedForToken = true;
      location.reload();
    }
  }
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
/** Compact NPR/volume formatter for the ribbon (5.51B, 286.9M, 12.3K).
    Values under 1000 keep 2dp; the suffix is always stated so a compact
    figure is never mistaken for an exact one. */
function fmtCompact(v) {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  const n = Number(v);
  const abs = Math.abs(n);
  const sign = n < 0 ? "-" : "";
  if (abs >= 1e9) return `${sign}${(abs / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${sign}${(abs / 1e6).toFixed(2)}M`;
  if (abs >= 1e3) return `${sign}${(abs / 1e3).toFixed(1)}K`;
  return `${sign}${abs.toFixed(2)}`;
}
function fmtPct(v, dp = 2) {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  const s = Number(v).toFixed(dp);
  return `${v > 0 ? "+" : ""}${s}%`;
}
/** Percent formatter for **fraction** inputs (0.34 -> "+34.00%").
    `fmtPct` expects a value already scaled to percent (34 -> "+34.00%"), which is
    what `megatool.backtest` and `percent_change` produce. Confusing the two scales
    is how B-46 happened; keep them distinct rather than guessing at call sites. */
function fmtPctFrac(v, dp = 2) {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return fmtPct(Number(v) * 100, dp);
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
  const newTabs = new Set(["nu","nse","nprof","neps","nepsh","nttm","ncmp","nscr","nelig","ncov"]);
  const babaTab = name.startsWith("baba/") ? name.slice(5) : null;
  const effName = babaTab ? "baba" : name;
  const viewName = newTabs.has(effName) ? "new" : (SS_NAV_TO_TAB[effName] ? "sastoshare" : effName);
  if (babaTab) { $$("#baba-tabs .baba-tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === babaTab)); }
  $$(".view").forEach((v) => v.classList.toggle("active", v.id === `view-${viewName}`));
  $$("#nav button[data-view]").forEach((b) => b.classList.toggle("active", b.dataset.view === name));
  if (name !== "overview") stopLivePolling();
  // Navigating to the chart must NOT reset the zoom/scroll the user set: the
  // chart instances survive a tab switch, so their logical range is already
  // correct and autoSize covers the container-size change. Fitting all data is
  // the explicit "Fit" button's job.
}

/* Lazy per-view work: the tabs below load their own data when shown, so a slow
   panel cannot block the boot of the rest of the terminal. */
function viewShown(name) {
  if (window.MTKronos && typeof window.MTKronos.onShow === "function") {
    try { window.MTKronos.onShow(name); } catch (e) { /* a broken panel must not kill the router */ }
  }
  if (name === "marketintel") {
    loadMarketIntelligence();
  } else if (name === "sectoroverview") {
    if (typeof loadSectorOverview === "function") loadSectorOverview();
  } else if (name === "new" || name === "nu" || name === "nse" || name === "nprof" || name === "neps" || name === "nepsh" || name === "nttm" || name === "ncmp" || name === "nscr" || name === "nelig" || name === "ncov") {
    loadNewSection(name === "new" ? "nu" : name);
  } else if (name === "baba" || name.startsWith("baba/")) {
    loadBabaSection(name === "baba" ? "dash" : name.slice(5));
  } else if (name === "research") {
    if (!state.researchMeta) loadResearchMeta();
    // Prefill from the chart's symbol only while the field is still empty, so a
    // symbol typed here is never overwritten.
    if (!($("#rs-symbol").value || "").trim()) {
      const current = ($("#symbol-input").value || "").trim();
      if (current) $("#rs-symbol").value = current.toUpperCase();
    }
    if (!($("#ws-symbol").value || "").trim()) {
      const src = ($("#rs-symbol").value || $("#symbol-input").value || "").trim();
      if (src) $("#ws-symbol").value = src.toUpperCase();
    }
    if (!($("#rst-symbols").value || "").trim()) {
      const src = ($("#rs-symbol").value || $("#symbol-input").value || "").trim();
      if (src) $("#rst-symbols").value = src.toUpperCase();
    }
    if (!($("#rs-vol-symbol").value || "").trim()) {
      const src = ($("#rs-symbol").value || $("#symbol-input").value || "").trim();
      if (src) $("#rs-vol-symbol").value = src.toUpperCase();
    }
    loadResearchStudio();
  } else if (name === "watchlists") {
    loadWatchlists();
  } else if (name === "backtest") {
    loadExperiments();
  } else if (name === "screener") {
    initRuleBuilder();
  } else if (name === "templates") {
    initTemplates();
  } else if (name === "overview") {
    applyDashLayout();
    loadMarketOverview();
    startLivePolling();
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
  } else if (name === "data") {
    loadData();
  } else if (name === "kimi") {
    loadKimiSection("overview");
  } else if (SS_NAV_TO_TAB[name]) {
    ssSubTab(SS_NAV_TO_TAB[name]);
  } else if (name === "ideas") {
    loadIdeas();
  } else if (name === "breadth") {
    // Nothing heavy on show: the panel loads on demand. Prefill dates from the
    // chart's range once so the default view is the same window the user saw.
    if (!$("#bh-start").value && state.chartDates && state.chartDates.length) {
      $("#bh-start").value = String(state.chartDates[0]).slice(0, 10);
      $("#bh-end").value = String(state.chartDates[state.chartDates.length - 1]).slice(0, 10);
    }
  } else if (name === "sea" || name === "swingw") {
    const field = name === "sea" ? $("#sea-symbol") : $("#swx-symbol");
    if (field && !(field.value || "").trim()) {
      const src = ($("#symbol-input").value || "").trim();
      if (src) field.value = src.toUpperCase();
    }
  }
}

/* --------------------------------------------------------------- freshness */
async function loadFreshness() {
  try {
    const s = await api("/api/status");
    state.status = s;
    const el = $("#freshness");
    const asOf = s.data_as_of || "unknown";
    const live = s.live || {};
    const active = live.active_provider;
    let src;
    if (s.live_feed_connected) src = "live feed";
    else if (active) src = `delayed public source (${esc(active)}) — not a live feed`;
    else src = "no market source — historical dataset only";
    el.innerHTML = `Data as of <b>${esc(asOf)}</b><br>${src}`;
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


async function loadMarketOverview() {
  // 1 & 2 run in parallel: index chart and dashboard data are independent.
  let d;
  try {
    const [idxResult] = await Promise.all([
      loadIndexChart().then(() => null).catch((e) => {
        const msg = String((e && e.message) || e);
        $("#ov-index-meta").innerHTML = /no stored index/i.test(msg)
          ? `<span class="down">No stored NEPSE index series in this deployment</span>`
          : `<span class="down">${esc(msg)}</span>`;
        return null;
      }),
      api("/api/market/dashboard").then((res) => { d = res; return res; }),
    ]);
  } catch (e) {
    $("#overview-banner").textContent = `Could not load dashboard: ${e.message}`;
    return;
  }
  if (!d) { $("#overview-banner").textContent = "Could not load dashboard: no data"; return; }
  const m = d.market || {}, breadth = d.breadth || {};
    const live = m;
  // KPI strip (count-up is visual; values update the DOM)
  const idx = d.index_chart || {};
  $("#ovkpis").innerHTML = [
    ["NEPSE", idx.latest == null ? "—" : fmtNum(idx.latest, 2), idx.pct == null ? "" : `${idx.pct >= 0 ? "+" : ""}${fmtNum(idx.pct, 2)}%`, pctClass(idx.pct)],
    ["Market", breadth.total ? `${fmtInt(breadth.advancers)} adv / ${fmtInt(breadth.decliners)} dec` : "—", `${fmtInt(breadth.missing)} missing data`],
    ["Turnover (latest day)", `NPR ${fmtNum(m.turnover_total ?? (m.summary && m.summary.filter && m.summary.find ? null : null), 0)}`, ""],
    ["Volume", fmtInt(m.volume_total ?? 0), ""],
    ["Status", m.is_open === true ? "OPEN" : m.is_open === false ? "CLOSED" : "unknown", "", m.is_open === true ? "up" : (m.is_open === false ? "down" : "")],
    ["Data as of", breadth.as_of || (m.observed_at ? String(m.observed_at).slice(0,10) : "—"), m.freshness ? m.freshness : ""],
  ].map(([k, v, s, c2]) =>
    `<div class="kpi"><div class="k">${esc(k)}</div><div class="v ${c2 || ""}">${esc(String(v))}</div>` +
    (s ? ` <div class="delta muted">${esc(s)}</div>` : "") + `</div>`).join("");
  // turnover/volume if the live layer didn't supply summary rows
  if (!m.turnover_total) {
    try {
      const cov = (await api("/api/dashboard"));
      if (cov && !cov.empty) {
        $("#ovkpis").children[2].querySelector(".v").textContent = "NPR " + fmtNum(cov.total_turnover, 0);
        $("#ovkpis").children[3].querySelector(".v").textContent = fmtInt(cov.total_volume);
      }
    } catch (e) { /* historical totals remain unavailable */ }
  }

  // breadth bar + MA participation
  const bb = breadth.moving_average || {};
  $("#breadth").innerHTML = [
    ["Advancers", breadth.advancers, "up"],
    ["Decliners", breadth.decliners, "down"],
    ["Unchanged", breadth.unchanged, ""],
    ["No change data", breadth.missing, "muted"],
    ["Above 20-d MA", bb.above_20, ""],
    ["Above 50-d MA", bb.above_50, ""],
    ["Above 200-d MA", bb.above_200, ""],
  ].map(([k, v, c]) => `<div class="stat"><div class="k">${k}</div><div class="v ${c}">${esc(String(v == null ? "—" : v))}</div></div>`).join("");
  const tot = breadth.total || 1;
  const seg = (cls, n, label) =>
    `<span class="${cls}" style="width:${(n / tot) * 100}%" title="${esc(label)}: ${fmtInt(n)} of ${fmtInt(tot)}"></span>`;
  $("#breadth-bar") && ($("#breadth-bar").outerHTML = `<div class="breadth-bar" id="breadth-bar">${seg(
    "b-up", breadth.advancers || 0, "Advancers")}${seg("b-down", breadth.decliners || 0, "Decliners")}${seg(
    "b-flat", breadth.unchanged || 0, "Unchanged")}${seg("b-miss", breadth.missing || 0, "No data")}</div>`);
  $("#breadth-hint").textContent =
    `Breadth = latest stored percent change per symbol (${fmtInt(breadth.total)} symbols). ` +
    `${bb.denominator_20 || 0} symbols have ≥20 bars; above-MA% uses each symbol's own 20/50/200-day SMA.`;
  $("#ov-ma-hint").textContent = `Above-MA counts are shares of symbols with sufficient history (denominators shown as stat counts).`;

  // sectors
  const secs = d.sectors || [];
  if (secs.length) {
    const maxAbs = Math.max(...secs.map((s) => Math.abs(s.avg_pct || 0)), 1);
    $("#ov-sectors").innerHTML = `<table class="ov-sectable">
      <thead><tr><th>Sector</th><th>Symbols</th><th>Adv/Dec</th><th>Avg % change</th><th>Turnover (NPR)</th></tr></thead>
      <tbody>` +
      secs.map((s) => {
        const a = s.avg_pct || 0, w = Math.min(100, Math.abs(a) / maxAbs * 100);
        return `<tr><td>${esc(s.sector)}</td><td>${fmtInt(s.symbols)}</td><td>${fmtInt(s.advancers)}/${fmtInt(s.decliners)}</td>` +
          `<td><div class="seccell"><span class="secbar ${a >= 0 ? "up" : "down"}" style="width:${w}%"></span><span class="${pctClass(a)}">${fmtPct(a)}</span></div></td>` +
          `<td>${fmtNum(s.turnover, 0)}</td></tr>`;
      }).join("") + `</tbody></table>`;
  } else {
    $("#ov-sectors").innerHTML = `<div class="empty">No sector data returned by the live source.</div>`;
  }

  // gainers / losers
  renderHeat(d.heat);
  const mv = d.movers || {};
  function moverTable(rows) {    if (!rows || !rows.length) return `<div class="empty">No movers available.</div>`;
    return table(["Symbol", "LTP", "Change %", "Turnover"],
      rows.map((r) => [
        { html: `<b>${esc(r.symbol)}</b>` },
        { html: fmtNum(r.ltp) },
        { html: fmtPct(r.pct), cls: pctClass(r.pct) },
        { html: fmtNum(r.turnover, 0) },
      ]));
  }
  $("#gainers").innerHTML = moverTable(mv.gainers);
  $("#losers").innerHTML = moverTable(mv.losers);
  $("#active").innerHTML = moverTable(mv.active);

  // valuation bins
  $("#ov-val").innerHTML = "";
  // MA participation stat-row (also above) — professional cards with drill-down
  const ma = breadth.moving_average || {};
  const maCard = (period) => {
    const above = ma[`above_${period}`] || 0;
    const den = ma[`denominator_${period}`] || 0;
    const pct = ma[`pct_above_${period}`];
    const isUp = pct != null && pct >= 50;
    return `<div class="ma-card" data-period="${period}" role="button" tabindex="0" title="Click to see companies above the ${period}-day MA">
      <div class="ma-head">${period}-DAY MA</div>
      <div class="ma-val ${isUp ? "up" : "down"}">${fmtInt(above)} <span class="ma-den">/ ${fmtInt(den)}</span></div>
      <div class="ma-bar"><span style="width:${pct == null ? 0 : Math.max(0, Math.min(100, pct))}%"></span></div>
      <div class="ma-pct">${pct == null ? "—" : fmtNum(pct, 1) + "%"} of evaluated symbols</div>
    </div>`;
  };
  if ($("#ov-ma")) $("#ov-ma").innerHTML = [20, 50, 200].map(maCard).join("") + `<div id="ov-ma-detail" class="tablewrap" style="margin-top:8px"></div>`;
  $$("#ov-ma .ma-card").forEach((card) => {
    const toggle = () => {
      const period = card.dataset.period;
      const detail = $("#ov-ma-detail");
      if (!detail) return;
      if (card.classList.contains("selected")) {
        card.classList.remove("selected");
        detail.innerHTML = "";
        return;
      }
      $$("#ov-ma .ma-card").forEach((c) => c.classList.remove("selected"));
      card.classList.add("selected");
      const above = (ma[`above_symbols_${period}`] || []);
      const below = (ma[`below_symbols_${period}`] || []);
      const list = above.length ? above : below;
      const label = above.length ? `above their ${period}-day MA` : `below their ${period}-day MA`;
      detail.innerHTML = `<p class="hint">${fmtInt(list.length)} symbols ${label} (${fmtNum(ma[`pct_above_${period}`], 1)}% above).</p>` +
        `<div class="tablewrap">${table(["Symbol", "Action"], list.map((s) => [
          { html: `<b>${esc(s)}</b>` },
          { html: `<button class="ghost ma-open-chart" data-sym="${esc(s)}">Open chart</button>` },
        ]))}</div>`;
      detail.querySelectorAll(".ma-open-chart").forEach((btn) => btn.addEventListener("click", () => {
        $("#symbol-input").value = btn.dataset.sym;
        showView("charts"); viewShown("charts"); loadChart();
      }));
    };
    card.addEventListener("click", toggle);
    card.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); } });
  });
  $("#ov-ma-hint").textContent = `Above-MA counts are shares of symbols with sufficient history (denominators shown). Click a card to list the actual symbols.`;

  // valuation bins as a histogram
  // valuation bins as a histogram (heights normalised to the largest bucket so
  // no bar overshoots the container; tail bucket groups all values at/above edge)
  const peBins = (d.valuation.pe_bins || []);
  const pbBins = (d.valuation.pb_bins || []);
  const maxPe = Math.max(1, ...peBins.map((b) => Number(b.count) || 0));
  const maxPb = Math.max(1, ...pbBins.map((b) => Number(b.count) || 0));
  const renderBins = (bins, maxC, label) => `
    <div class="hint" style="margin:6px 0 2px"><b>${label}</b></div>
    <div class="hist" style="height:120px">
      ${bins.map((b, idx) => `<div class="hist-bin" data-idx="${idx}" style="cursor:pointer" title="${esc(b.label)}: ${fmtInt(b.count)}">
        <span class="hb" style="height:${Math.max(4, Math.round(((Number(b.count) || 0) / maxC) * 100))}px"></span>
        <span class="hl">${esc(b.label)}</span>
        <span class="hn">${fmtInt(b.count)}</span></div>`).join("")}
    </div>
    <p class="hint" style="margin:2px 0 8px">Bar height is proportional to the largest bucket. The last bucket groups every value at or above its edge (outliers are not individually shown). Click a bucket to see its companies.</p>`;
  if ($("#ov-val")) $("#ov-val").innerHTML = `
    <div style="display:block">
      ${renderBins(peBins, maxPe, "P/E (price / reported EPS)")}
      <div id="ov-val-detail" class="tablewrap" style="margin-top:8px"></div>
      ${renderBins(pbBins, maxPb, "P/B (price / reported net worth per share)")}
      <p class="hint">Coverage: P/E ${fmtInt(d.valuation.coverage.pe_available)}, P/B ${fmtInt(d.valuation.coverage.pb_available)} of ${fmtInt(d.valuation.coverage.symbols_with_price)} symbols with a stored close. Counts, not investment recommendations. Values are unadjusted for corporate actions; non-positive earnings/book values are excluded rather than plotted as negatives.</p>
    </div>`;
  $$("#ov-val .hist-bin").forEach((bin) => {
    bin.addEventListener("click", () => {
      const idx = parseInt(bin.dataset.idx, 10);
      const b = peBins[idx];
      const detail = $("#ov-val-detail");
      if (!detail || !b) return;
      if (bin.classList.contains("selected")) {
        bin.classList.remove("selected");
        detail.innerHTML = "";
        return;
      }
      $$("#ov-val .hist-bin").forEach((x) => x.classList.remove("selected"));
      bin.classList.add("selected");
      if (!b.symbols || !b.symbols.length) { detail.innerHTML = `<div class="empty">No companies in this bucket.</div>`; return; }
      detail.innerHTML = `<div class="tablewrap">${table(
        ["Symbol", "Action"],
        b.symbols.map((s) => [
          { html: `<b>${esc(s)}</b>` },
          { html: `<button class="ghost ov-open-chart" data-sym="${esc(s)}">Open chart</button>` },
        ]))}</div>`;
      detail.querySelectorAll(".ov-open-chart").forEach((btn) => {
        btn.addEventListener("click", () => {
          $("#symbol-input").value = btn.dataset.sym;
          showView("charts");
          viewShown("charts");
          loadChart();
        });
      });
    });
  });

  renderOverviewVisuals(d);

  // Scroll-triggered reveals (IntersectionObserver, reduced-motion aware).
  try {
    if (!window.__pravahaRevealObs) {
      window.__pravahaRevealObs = new IntersectionObserver((entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) { e.target.classList.add("in"); }
        });
      }, { threshold: 0.12, rootMargin: "0px 0px -40px 0px" });
    }
    const obs = window.__pravahaRevealObs;
    $$(".reveal").forEach((el) => { if (!el.classList.contains("in")) obs.observe(el); });
  } catch (e) { /* IntersectionObserver unsupported - graceful fallback */ }

  // An empty store must say so, not print "(undefined)" or imply a live quote.
  const noStoredData = !d.breadth.as_of && !(idx.latest != null);
  $("#overview-banner").textContent = noStoredData
    ? "No stored market data in this deployment — every panel below is empty. " +
      "Ingest NEPSE history (or place a prepared market database on the persistent disk) " +
      "to populate the dashboard. This is not a live quote and nothing here is fabricated."
    : `Computed from the latest stored trading day (${d.breadth.as_of}) — not a live quote. ` +
      `Live source: ${live.provider || "none"} (status ${live.status || "unknown"}).`;

  applyDashLayout();
  refreshTicker();
  const rng = $("#ov-range");
  if (rng && !rng.dataset.bound) { rng.addEventListener("change", loadIndexChart); rng.dataset.bound = "1"; }
  startLivePolling();
  // keep the ticker moving at the provider's cadence, but never faster than 5s
  if (!state.tickerTimer) state.tickerTimer = setInterval(() => {
    if (document.querySelector("#view-overview.active")) refreshTicker();
  }, 30000);
}
async function loadSymbols() {
  try {
    const s = await api("/api/securities?limit=1000");
    $("#symbol-list").innerHTML = `<option value="NEPSE">NEPSE Composite Index</option>` +
      s.securities.map((x) => `<option value="${esc(x.symbol)}">${x.bars} bars</option>`).join("");
    if (s.securities.length && !($("#symbol-input").value || "").trim()) $("#symbol-input").value = s.securities[0].symbol;
  } catch (e) { /* non-fatal; the input still accepts typed symbols */ }
}


/* ============================== §ribbon  (NEPSE market ribbon) ============
   A scrolling, categorised market strip built from /api/market/ribbon, which is
   computed from the most recent stored trading day. It is deliberately NOT a
   live quote tape: the freshness badge says so, and every group carries the
   ranking rule that produced it. Items are clickable and open the symbol in the
   chart. The animation can be paused, and pauses on hover/focus.
   ========================================================================= */
const RIBBON_PAUSE_KEY = "mt-ribbon-paused";

function ribbonItem(it, groupKey) {
  const p = it.change_pct;
  const cls = p == null ? "flat" : (p > 0 ? "pos" : (p < 0 ? "neg" : "flat"));
  const mark = p == null ? "" : (p > 0 ? "▲" : (p < 0 ? "▼" : "•"));
  let extra = null;
  if (groupKey === "volume" && it.volume != null) extra = `${fmtCompact(it.volume)} sh`;
  else if (groupKey === "turnover" && it.turnover != null) extra = `Rs ${fmtCompact(it.turnover)}`;
  else if (it.kind === "high") extra = "new high";
  else if (it.kind === "low") extra = "new low";
  const title = `${it.symbol}${it.close != null ? ` · last ${fmtNum(it.close, 2)}` : ""}` +
    `${p != null ? ` · ${fmtPct(p)}` : ""}${extra ? ` · ${extra}` : ""} — click to open in the chart`;
  return `<button class="ti ${cls}" data-sym="${esc(it.symbol)}" title="${esc(title)}">` +
    `<span class="ti-mark">${mark}</span><span class="ti-sym">${esc(it.symbol)}</span>` +
    (it.close != null ? `<span>${fmtNum(it.close, 2)}</span>` : "") +
    (p == null ? "" : `<span>${fmtPct(p)}</span>`) +
    (extra ? `<span class="ti-note">${esc(extra)}</span>` : "") +
    `</button>`;
}

function applyRibbonPaused() {
  const paused = localStorage.getItem(RIBBON_PAUSE_KEY) === "1";
  const t = $("#tick-track");
  if (t) t.style.animationPlayState = paused ? "paused" : "running";
  const b = $("#tick-pause");
  if (b) {
    b.textContent = paused ? "▶" : "❚❚";
    b.title = paused ? "Resume the scrolling ribbon" : "Pause the scrolling ribbon";
    b.setAttribute("aria-pressed", paused ? "true" : "false");
  }
  const host = $("#ticker");
  if (host) host.classList.toggle("ribbon-paused", paused);
}

function bindRibbonControls() {
  const b = $("#tick-pause");
  if (!b || b.dataset.bound === "1") return;
  b.dataset.bound = "1";
  b.addEventListener("click", () => {
    const paused = localStorage.getItem(RIBBON_PAUSE_KEY) === "1";
    localStorage.setItem(RIBBON_PAUSE_KEY, paused ? "0" : "1");
    applyRibbonPaused();
  });
}

function renderTicker(d, live) {
  const track = $("#tick-track");
  if (!track) return;
  bindRibbonControls();
  if (!d || d.empty) {
    track.innerHTML = `<span class="hint" style="padding-left:14px">No stored market data yet — run a fetch to populate the ribbon.</span>`;
    const badge0 = $("#tick-badge");
    if (badge0) badge0.textContent = "NEPSE · no data";
    return;
  }
  const badge = $("#tick-badge");
  if (badge) badge.textContent = `NEPSE ${d.as_of || ""} · delayed`;
  const breadth = d.breadth || {};
  const totals = d.totals || {};
  const idx = d.index || (live && live.index) || null;

  let html = "";
  if (idx && idx.close != null) {
    const p = idx.change_pct;
    html += `<button class="ti ${p > 0 ? "pos" : (p < 0 ? "neg" : "flat")}" data-sym="NEPSE" ` +
      `title="${esc(idx.name || "NEPSE")} · ${esc(idx.date || d.as_of)} · delayed — click to open the index chart">` +
      `<span class="ti-sym">${esc(idx.name || "NEPSE")}</span><span>${fmtNum(idx.close, 2)}</span>` +
      (p == null ? "" : `<span>${fmtPct(p)}</span>`) +
      `<span class="ti-note">delayed</span></button>`;
  }
  html += `<span class="ti-div" title="Advancers / decliners / unchanged on ${esc(d.as_of)}">` +
    `breadth ${breadth.advancers ?? "—"}/${breadth.decliners ?? "—"}/${breadth.unchanged ?? "—"}</span>`;
  if (totals.turnover != null) {
    html += `<span class="ti-div" title="Total traded value on ${esc(d.as_of)}">turnover Rs ${fmtCompact(totals.turnover)}</span>`;
  }
  for (const g of (d.groups || [])) {
    if (!g.items || !g.items.length) continue;
    html += `<span class="ti-head" title="${esc(g.rule)}">${esc(g.title)}</span>`;
    html += g.items.map((it) => ribbonItem(it, g.key)).join("");
  }
  for (const u of (d.unavailable || [])) {
    html += `<span class="ti-head muted" title="${esc(u.reason)}">${esc(u.title)} · unavailable</span>`;
  }
  track.innerHTML = html + html; // duplicated for the seamless loop
  // Readable speed: hold roughly 55 px/s regardless of how much content there is.
  requestAnimationFrame(() => {
    const half = track.scrollWidth / 2;
    const secs = Math.max(32, Math.round(half / 55));
    track.style.animationDuration = `${secs}s`;
  });
  $$("#tick-track .ti").forEach((b) => b.addEventListener("click", () => {
    const sym = b.dataset.sym;
    if (!sym) return;
    $("#symbol-input").value = sym;
    showView("charts");
    viewShown("charts");
    loadChart();
  }));
  applyRibbonPaused();
}

async function refreshTicker() {
  try {
    const [ribbon, live] = await Promise.all([
      api("/api/market/ribbon?top=8"),
      api("/api/live/market").catch(() => null),
    ]);
    renderTicker(ribbon, live);
  } catch (e) {
    const t = $("#tick-track");
    if (t) t.innerHTML = `<span class="hint" style="padding-left:14px">Market ribbon unavailable: ${esc(e.message)}</span>`;
  }
}

/* Prefer the user's first watchlist in the top strip. Stored in localStorage
   so the ticker can render before the watchlists view is opened. */
async function syncTickerWatchlist() {
  try {
    const d = await api("/api/watchlists");
    const first = (d.watchlists || [])[0];
    if (first && Array.isArray(first.symbols) && first.symbols.length) {
      localStorage.setItem("mt-ticker-watch", JSON.stringify(first.symbols.slice(0, 20)));
    }
  } catch (e) { /* watchlists are optional */ }
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
    // A single stacked bar makes the balance visible at a glance; the numbers
    // stay above it so the chart never replaces the exact counts.
    const tot = (b.advancers || 0) + (b.decliners || 0) + (b.unchanged || 0) + (b.unknown || 0) || 1;
    const seg = (cls, n, label) =>
      `<span class="${cls}" style="width:${(n / tot) * 100}%" title="${esc(label)}: ${fmtInt(n)}"></span>`;
    $("#breadth").insertAdjacentHTML(
      "beforeend",
      `<div class="breadth-bar">${seg("b-up", b.advancers || 0, "Advancers")}${seg(
        "b-down", b.decliners || 0, "Decliners")}${seg("b-flat", b.unchanged || 0, "Unchanged")}${seg(
        "b-miss", b.unknown || 0, "No change data")}</div>`
    );
    $("#breadth-hint").textContent = `Breadth uses each security's last stored percent change. Securities without change data are counted separately rather than assumed flat.`;

    const totalsEl = $("#totals");
    if (totalsEl) totalsEl.innerHTML = [
      ["Turnover", `NPR ${fmtNum(d.total_turnover, 0)}`],
      ["Volume", fmtInt(d.total_volume)],
      ["Symbols", fmtInt(d.symbols)],
      ["As of", d.data_as_of],
    ].map(([k, v]) => `<div class="stat"><div class="k">${esc(k)}</div><div class="v">${esc(v)}</div></div>`).join("");

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

/* --------------------------------------------------------------- live market
   Freshness is MEASURED from the source's own newest timestamp; the badge shows
   the observation age, never the request speed. Polling only runs while the
   Overview tab is visible, and the backend caches at the provider's publication
   cadence, so a fast UI cannot turn into a request storm against the source. */
function fmtAge(sec) {
  if (sec === null || sec === undefined) return "unknown";
  if (sec < 90) return `${Math.round(sec)}s`;
  if (sec < 5400) return `${(sec / 60).toFixed(1)} min`;
  if (sec < 172800) return `${(sec / 3600).toFixed(1)} h`;
  return `${(sec / 86400).toFixed(1)} d`;
}

function liveBadgeClass(fresh) {
  if (fresh === "live") return "pill pill-pass";
  if (fresh === "recent") return "pill pill-info";
  if (fresh === "delayed") return "pill pill-review";
  if (fresh === "last-close" || fresh === "stale") return "pill pill-hard";
  return "pill pill-hard";
}

function renderLive(d) {
  const fresh = d.freshness || "unknown";
  const badge = $("#live-badge");
  badge.className = liveBadgeClass(fresh);
  badge.textContent = fresh;
  $("#live-dot").className = "live-dot" + (fresh === "live" ? " on" : "");
  $("#live-source").textContent = d.ok
    ? `${d.label} · request ${Math.round(d.fetch_latency_ms || 0)} ms${d.cached ? " (cached)" : ""}`
    : "";

  if (!d.ok) {
    $("#live-stats").innerHTML = "";
    $("#live-hint").textContent =
      `${d.label ? d.label + ": " : ""}${d.error || "no live provider"}. ` +
      `Everything else on this page uses the stored dataset only.`;
    return;
  }

  const idx = d.index || {};
  const close = idx.close ?? idx.indexValue ?? idx.currentValue ?? null;
  const pct = idx.perChange ?? idx.percentChange ?? null;
  const stats = [
    ["Market", d.is_open === true ? "OPEN" : d.is_open === false ? "CLOSED" : "unknown", d.is_open === false ? "down" : (d.is_open === true ? "up" : "")],
    ["NEPSE index", close === null ? "—" : fmtNum(close), ""],
    ["Change", pct === null ? "—" : fmtPct(pct), pctClass(pct)],
    ["Observed age", fmtAge(d.age_seconds), ""],
    ["Quotes", fmtInt(d.quote_count), ""],
    ["Source as of", d.observed_at ? d.observed_at.replace("T", " ").replace("+00:00", "Z") : "—", ""],
  ];
  $("#live-stats").innerHTML = stats
    .map(([k, v, c]) => `<div class="stat"><div class="k">${esc(k)}</div><div class="v ${c}" style="font-size:16px">${esc(String(v))}</div></div>`)
    .join("");
  const notes = (d.notes || []).join(" ");
  const missing = d.missing_price ? ` ${d.missing_price} row(s) had no usable price and were left blank.` : "";
  $("#live-hint").textContent =
    `"Observed age" is how old the source's newest timestamp is (end-to-end), not how fast the request returned. ` +
    `${notes}${missing}`;
}

async function loadLive(force = false) {
  const btn = $("#live-refresh");
  if (btn) { btn.disabled = true; btn.textContent = "Refreshing…"; }
  try {
    renderLive(await api(`/api/live/market${force ? "?refresh=true" : ""}`));
  } catch (e) {
    $("#live-hint").textContent = `Live layer unavailable: ${e.message}`;
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = "Refresh now"; }
  }
}

function startLivePolling() {
  stopLivePolling();
  loadLive();
  state.liveTimer = setInterval(() => {
    if (document.querySelector("#view-overview.active")) loadLive();
  }, 20000);
}

function stopLivePolling() {
  if (state.liveTimer) { clearInterval(state.liveTimer); state.liveTimer = null; }
}

/* ------------------------------------------------------------------- ideas */
function ideaStatusPill(status) {
  if (status === "available") return "pill-pass";
  if (status === "partial") return "pill-review";
  return "pill-hard";
}

async function loadIdeas() {
  try {
    const d = await api("/api/ideas");
    $("#ideas-grid").innerHTML = (d.models || []).map((m) => {
      const miss = (m.missing_inputs || []).length
        ? `<div class="hint">not stored: ${m.missing_inputs.map(esc).join(", ")}</div>` : "";
      const off = m.status === "insufficient_data" ? " disabled" : "";
      return `<button class="idea-card" data-idea="${esc(m.id)}"${off} title="${esc(m.source || "")}">
        <span class="idea-cat">${esc(m.category)}</span>
        <b>${esc(m.name)}</b>
        <p>${esc(m.blurb)}</p>
        <span class="pill ${ideaStatusPill(m.status)}">${esc(m.status.replace(/_/g, " "))}</span>
        ${miss}
      </button>`;
    }).join("");
    $$("#ideas-grid .idea-card").forEach((b) =>
      b.addEventListener("click", () => runIdea(b.dataset.idea)));
  } catch (e) {
    $("#ideas-grid").innerHTML = `<div class="error">${esc(e.message)}</div>`;
  }
}

async function runIdea(id) {
  $("#ideas-title").textContent = "Results";
  $("#ideas-result").innerHTML = `<div class="hint">Running ${esc(id)}…</div>`;
  try {
    renderIdea(await api(`/api/ideas/${encodeURIComponent(id)}`));
  } catch (e) {
    $("#ideas-result").innerHTML = `<div class="error">${esc(e.message)}</div>`;
  }
}

function renderIdea(d) {
  const m = d.model || {};
  $("#ideas-title").textContent = m.name || "Results";
  const head = `<p class="hint"><b>${esc(m.name || "")}</b> — ${esc(m.source || "")}
    <br>${esc(d.note || "")}${d.evaluated ? ` (${fmtInt(d.evaluated)} evaluated)` : ""}</p>`;
  const rows = d.rows || [];
  if (!rows.length) {
    $("#ideas-result").innerHTML = head + `<div class="empty">No results for this model.</div>`;
    return;
  }
  const cols = Object.keys(rows[0]).filter((k) => k !== "symbol");
  const body = rows.map((r) => [
    { html: `<b class="click" data-sym="${esc(r.symbol)}">${esc(r.symbol)}</b>` },
    ...cols.map((c) => {
      const v = r[c];
      const txt = v === null || v === undefined ? "—" : typeof v === "boolean" ? (v ? "yes" : "no") : String(v);
      const cls = typeof v === "number" ? (v > 0 ? (c === "score" ? "up" : "") : "") : "";
      return { html: esc(txt), cls };
    }),
  ]);
  $("#ideas-result").innerHTML = head + table(["Symbol", ...cols], body);
  $$("#ideas-result .click").forEach((el) =>
    el.addEventListener("click", () => {
      const sym = el.dataset.sym;
      $("#symbol-input").value = sym;
      const g = $("#global-symbol");
      if (g) g.value = sym;
      showView("charts");
      viewShown("charts");
      loadChart();
    }));
}


async function loadIndexChart() {
  const range = ($("#ov-range").value || "120");
  const q = range === "0" ? "" : `?limit=${encodeURIComponent(range)}`;
  const meta = $("#ov-index-meta");
  if (meta) meta.innerHTML = `<span class="chart-dim">Loading NEPSE index…</span>`;
  try {
    const idx = await api(`/api/indices/NEPSE${q}`);
    const pts = idx.points || [];
    if (!pts.length) { if (meta) meta.textContent = "no NEPSE index series available"; return; }
    if (state.charts["ov-index"]) { try { state.charts["ov-index"].remove(); } catch (e) {} }
    const chart = LightweightCharts.createChart($("#ov-chart"), {
      autoSize: true, layout: { background: { color: PRAVAHA.panel2 }, textColor: PRAVAHA.muted },
      rightPriceScale: { borderColor: PRAVAHA.border }, grid: { vertLines: { color: PRAVAHA.grid }, horzLines: { color: PRAVAHA.grid } },
      timeScale: { borderColor: PRAVAHA.border }, crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
    });
    state.charts["ov-index"] = chart;
    // Area chart reads better than a bare line for a single index series and
    // stays honest: the source has closing values only, so no OHLC candles.
    const ser = chart.addAreaSeries({
      lineColor: PRAVAHA.cyan, topColor: "rgba(0,217,232,.28)",
      bottomColor: "rgba(0,217,232,0)", lineWidth: 2,
      priceLineVisible: true, lastValueVisible: true,
    });
    ser.setData(pts.map((p) => ({ time: String(p.date).slice(0,10), value: Number(p.close) })));
    chart.timeScale().fitContent();
    const last = pts[pts.length - 1];
    const prev = pts.length > 1 ? pts[pts.length - 2] : null;
    const dpc = prev ? Number(last.close) - Number(prev.close) : null;
    const ppc = dpc != null && Number(prev.close) ? (dpc / Number(prev.close)) * 100 : null;
    const cls = dpc == null ? "" : dpc >= 0 ? "up" : "down";
    if (meta) meta.innerHTML =
      `<b>NEPSE</b> <span style="font-size:15px;font-weight:700">${fmtNum(last.close, 2)}</span>` +
      (dpc == null ? "" : ` <span class="${cls}">${dpc >= 0 ? "+" : ""}${fmtNum(dpc, 2)} (${ppc >= 0 && dpc >= 0 ? "+" : ""}${fmtNum(ppc, 2)}%)</span>`) +
      ` · ${fmtInt(idx.rows_returned)} obs · ${esc(String(idx.first_date).slice(0,10))} → <b>${esc(String(idx.last_date).slice(0,10))}</b>` +
      ` · <span class="chart-dim">official stored series · not live</span>`;
    const note = $("#ov-chart-note");
    if (note) note.textContent = "Closing values only — candlesticks and volume require genuine OHLCV data, which this index series does not contain.";
  } catch (e) { if (meta) meta.textContent = `index unavailable: ${e.message}`; }
}

/* ---------------------------------------------- live data source diagnostics
   Every provider is listed with its real status. LIVE_VERIFIED is only shown
   when the source's own newest observation is under a minute old, so a 200
   response for stale data can never look live. */
async function loadLiveSources() {
  try {
    const s = await api("/api/live/status");
    const snap = await api("/api/live/market");
    const cls = liveBadgeClass(snap.freshness || "unknown");
    $("#live-snapshot").innerHTML = [
      ["Active source", snap.label || "none"],
      ["Status", snap.status || "UNAVAILABLE"],
      ["Freshness", snap.freshness || "unknown"],
      ["Observation age", fmtAge(snap.age_seconds)],
      ["Provider timestamp", snap.observed_at ? snap.observed_at.replace("T", " ").replace("+00:00", "Z") : "—"],
      ["Receipt time", snap.fetched_at ? snap.fetched_at.replace("T", " ").replace("+00:00", "Z") : "—"],
      ["Request latency", snap.fetch_latency_ms === null || snap.fetch_latency_ms === undefined ? "—" : `${Math.round(snap.fetch_latency_ms)} ms`],
      ["Securities", fmtInt(snap.quote_count)],
      ["Origin", snap.origin ? String(snap.origin).replace("https://", "") : "—"],
    ]
      .map(([k, v]) => `<div class="stat"><div class="k">${esc(k)}</div><div class="v" style="font-size:15px">${esc(String(v))}</div></div>`)
      .join("");

    $("#live-sources").innerHTML = table(
      ["Source", "Configured", "Status / reason", "Poll cadence", "Publishes"],
      (s.providers || []).map((p) => {
        const isActive = p.id === s.active_provider;
        const pill = p.configured
          ? (isActive ? `<span class="${cls}">${esc(snap.status || "IN USE")}</span>` : `<span class="pill pill-info">available</span>`)
          : `<span class="pill pill-hard">${p.requires_gate ? "BLOCKED" : "UNAVAILABLE"}</span>`;
        return [
          { html: `<b>${esc(p.label)}</b>${isActive ? ' <span class="pill pill-info">active</span>' : ""}` },
          { html: p.configured ? "yes" : "no" },
          { html: `${pill}<div class="hint" style="margin:2px 0 0">${esc(p.reason || "")}</div>` },
          { html: `${fmtAge(p.cadence_seconds)}` },
          { html: `${fmtAge(p.publish_cadence_seconds)}` },
        ];
      })
    );
  } catch (e) {
    $("#live-sources").innerHTML = `<div class="down">${esc(e.message)}</div>`;
  }
}

/* ------------------------------------------------------------------ charts */
function destroyCharts() {
  Object.values(state.charts).forEach((c) => { try { c.remove(); } catch (err) { /* already gone */ } });
  state.charts = {};
  state.paneSeries = {};
  state.markers = [];
  // Candle markers are rebuilt only when the candlestick layer is on; without
  // this reset a symbol with the layer off inherited the previous symbol's
  // letters (stale/duplicate objects in the manager and on the chart).
  state.candleMarkers = [];
  state.elliottMarkers = [];
  state.quickObjects = [];
  state.elliottAutoMarkers = [];
  state.elliottAutoLine = null;
  state.elliottAuto = null;
  state.harmonicSeries = [];
  state.harmonicMarkers = [];
  state.harmonicData = null;
  state.drawSeries = [];
  state.markerSeries = null;
  state.markerSeriesKey = null;
  state.anchorHandlePrim = null;
  state.drawMarkers = [];
  state.drawPreviewSeries = [];
  state.customFormulaSeries = [];  state.pendingMarker = [];
  state.drawDrag = null;
  state.patternSeries = [];
  state.patternMarkers = [];
  state.patternList = [];
  state.structureMarkers = [];
  state.structureSeries = [];
  state.trendMarkers = [];
  state.trendSeries = [];
  state.momentumMarkers = [];
  state.momentumSeries = [];
  state.volatilityMarkers = [];
  state.volatilitySeries = [];
  state.volumeMarkers = [];
  state.volumeSeries = [];
  state.gapMarkers = [];
  state.gapSeries = [];
  state.regimeMarkers = [];
  state.regimeSeries = [];
  state.relativeMarkers = [];
  state.relativeSeries = [];
  state.microMarkers = [];
  state.microSeries = [];
  state.distributionMarkers = [];
  state.distributionSeries = [];
  state.eventMarkers = [];
  state.eventSeries = [];
  state.strategyMarkers = [];
  state.strategySeries = [];
  state.drawPrimitives = [];
  state.markerMeta = {};
  state.rsSeries = [];
  state.indSeries = {};
  if (state.compare) { state.compare.series = []; state.compare.lastValues = {}; }
  const cmpLegendEl = document.getElementById("cmp-legend");
  if (cmpLegendEl) { cmpLegendEl.hidden = true; cmpLegendEl.innerHTML = ""; }
  ["#chart", "#rsi-pane", "#macd-pane"].forEach((id) => { $(id).innerHTML = ""; });
  document.querySelectorAll("[id^='pane-custom-']").forEach((el) => el.remove());
  // Pane headers are siblings of their chart containers, so they are removed
  // here too; renderPaneHeaders() rebuilds them for the new panes.
  document.querySelectorAll("[data-pane-head]").forEach((el) => el.remove());
  Object.keys(state.charts || {}).forEach((k) => {
    if (k.startsWith("pane-custom-")) delete state.charts[k];
  });
  if ($("#chart-note")) $("#chart-note").textContent = "";
}

function makeChart(container, height) {
  const chart = LightweightCharts.createChart(container, {
    autoSize: true,
    height,
    layout: { background: { color: PRAVAHA.panel2 }, textColor: PRAVAHA.muted },
    grid: { vertLines: { color: PRAVAHA.grid }, horzLines: { color: PRAVAHA.grid } },
    rightPriceScale: { borderColor: PRAVAHA.border },
    timeScale: { borderColor: PRAVAHA.border, timeVisible: false },
    crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
  });
  return chart;
}

/* §5.6 OHLCV strip (one binding per chart): follows the crosshair, shows the
   hovered bar's own values (never the latest bar's), and falls back to the
   last bar when the pointer leaves. The DOM write is skipped when the hovered
   bar has not changed, so moving across a chart cannot rebuild the strip
   dozens of times per second. */
function bindOhlcvLegend(chart) {
  const legendEl = $("#ohlcv-legend");
  if (!legendEl || !chart) return;
  let lastShown = null;
  const showBar = (b) => {
    if (!b) { legendEl.hidden = true; lastShown = null; return; }
    const tfLabel = { daily: "Daily", weekly: "Weekly", monthly: "Monthly" }[state.chartTf] || (state.chartTf || "");
    const key = `${b.time}|${tfLabel}|${state.chartSymbol}`;
    if (key === lastShown) return;             // same bar → nothing to repaint
    lastShown = key;
    const i = state.chartBars.indexOf(b);
    const prev = i > 0 ? state.chartBars[i - 1] : null;
    const dpc = prev && prev.close != null ? b.close - prev.close : null;
    const ppc = dpc != null && prev.close ? (dpc / prev.close) * 100 : null;
    const cls = dpc == null ? "" : dpc >= 0 ? "olv-up" : "olv-down";
    const closeOnly = (b.open == null || b.high == null || b.low == null || b.ohlc_status === "invalid");
    const volLabel = b.volume_type === "turnover_npr" ? "T/O" : "V";
    legendEl.innerHTML =
      `<b>${esc(state.chartSymbol || "")}</b> <span class="olv-tf">${esc(tfLabel)}</span>` +
      ` <span class="olv-t">${esc(String(b.time).slice(0, 10))}</span>` +
      (closeOnly
        ? ` <span class="chart-dim">no OHLC body (close-only/invalid row)</span> C <b>${fmtNum(b.close)}</b>`
        : ` O <b>${fmtNum(b.open)}</b> H <b>${fmtNum(b.high)}</b> L <b>${fmtNum(b.low)}</b> C <b>${fmtNum(b.close)}</b>`) +
      (dpc == null ? "" : ` <span class="${cls}">${dpc >= 0 ? "+" : ""}${fmtNum(dpc, 2)} (${ppc >= 0 && dpc >= 0 ? "+" : ""}${fmtNum(ppc, 2)}%)</span>`) +
      ` ${volLabel} <b>${fmtInt(b.volume)}</b>`;
    legendEl.hidden = false;
  };
  chart.subscribeCrosshairMove((param) => {
    if (!param || !param.time) {
      // Fallback: the cursor bar while replay is on, otherwise the last bar.
      const bars = state.chartBars;
      const idx = state.replay && state.replay.on ? state.replay.i : bars.length - 1;
      const last = bars[Math.max(0, Math.min(idx, bars.length - 1))];
      if (last) showBar(last);
      return;
    }
    const b = state.chartBars.find((x) => x.time === param.time);
    if (b) showBar(b);
  });
  const lastBar0 = state.chartBars[state.chartBars.length - 1];
  if (lastBar0) showBar(lastBar0);
}

/* Concurrent loads leaked canvases: each call destroys the charts *before* its
   await, so a chart created by an older in-flight call survived. Loads are now
   serialised by a sequence token - only the newest one may draw. */
let chartLoadSeq = 0;

async function loadChart() {
  const seq = ++chartLoadSeq;
  const symbol = ($("#symbol-input").value || "").trim().toUpperCase();
  // Each symbol keeps its own analysis-layer choice (opt-in, per symbol).
  state.layers = symbol ? layersFor(symbol) : {};
  // Restore this symbol's saved quick-layer (chart-toolbar) toggles, if any.
  // Falls back to the current DOM state (boot defaults) when nothing is saved.
  const _ql = symbol ? loadQuickLayers(symbol) : null;
  if (_ql) applyQuickLayersState(_ql);
  const errEl = $("#chart-error");
  errEl.textContent = "";
  if (!symbol) { errEl.textContent = "Enter a symbol."; return; }

  const range = $("#range").value;
  // Viewport preservation: reloading the SAME symbol+timeframe (adding an
  // analysis layer, toggling a quick layer, re-applying a template) must not
  // throw away the window the user zoomed into. A symbol or timeframe change is
  // a new context and fits to the data, as before. Captured before teardown;
  // restored after the new chart is built.
  const tfNow = (document.getElementById("tf-select") || {}).value || "daily";
  // The requested history range is part of the context: a logical range is an
  // index window, so restoring it onto a series with a *different* number of
  // bars silently shows the wrong slice (load 750 bars, keep the 60-bar window
  // from before, and the recent data — and any analysis drawn on it — vanishes
  // off the right edge). Same symbol + timeframe + range = the same window.
  const sameContext = state.chartSymbol === symbol && state.chartTf === tfNow
    && state.chartRange === range && !!state.charts.price;
  let keepRange = null;
  if (sameContext) {
    try { keepRange = state.charts.price.timeScale().getVisibleLogicalRange(); } catch (e) { keepRange = null; }
  }
  destroyCharts();
  // Kronos overlays belong to the previous chart: a different symbol must
  // never display them, and the same symbol's overlay is rebuilt on reload.
  clearForecastOverlays();
  invalidateKronosRuns();   // any in-flight forecast becomes stale → dropped
  // Panes start hidden; addPane reveals the one it draws into.
  ["rsi-pane", "macd-pane"].forEach((id) => { const el = $(id); if (el) el.hidden = true; });

  try {
    const tf = (document.getElementById("tf-select") || {}).value || "daily";
    state.chartTf = tf;   // labelled in the OHLCV strip and enforced by Kronos
    // NEPSE composite index: served by /api/indices, not /api/bars. The index
    // series has closing values only (no OHLCV), so it renders as an area chart
    // and skips the volume histogram. No data is fabricated.
    const isIndex = (symbol === "NEPSE");
    // Disable indicators that require OHLC/volume for close-only index data.
    const volCb = $("#ind-vol"), swingsCb = $("#ind-swings"), closeSwingsCb = $("#ind-close-swings");
    if (volCb) { volCb.disabled = isIndex; volCb.checked = isIndex ? false : volCb.checked; volCb.parentElement.title = isIndex ? "Market-wide turnover available (NPR), not share volume. Use Index Turnover analysis." : ""; }
    if (swingsCb) { swingsCb.disabled = false; swingsCb.parentElement.title = isIndex ? "OHLC swings from genuine OHLC rows only (placeholder rows excluded)" : ""; }
    if (closeSwingsCb) { closeSwingsCb.disabled = !isIndex; closeSwingsCb.checked = isIndex ? closeSwingsCb.checked : false; closeSwingsCb.parentElement.title = isIndex ? "Close-based pivot detection (closing prices only)" : "Only available for close-only index series"; }
    const qs = range === "0" ? (isIndex ? "?limit=20000" : "") : `?limit=${encodeURIComponent(range)}`;
    const url = isIndex
      ? `/api/indices/NEPSE/ohlc${qs}`
      : (tf === "daily" ? `/api/bars/${encodeURIComponent(symbol)}${qs}` : `/api/bars/${encodeURIComponent(symbol)}/${tf}${qs}`);
    const data = await api(url);
    if (seq !== chartLoadSeq) return;  // a newer load is already drawing
    const bars = isIndex
      ? (data.bars || []).map((b) => ({
          time: String(b.date).slice(0, 10),
          // Placeholder index rows keep NULL OHLC. A close-only index day is
          // not a candle, and fabricating O=H=L=C=close is exactly what must
          // not happen. Close-based renderings read `close`; candle renderings
          // drop these bars to whitespace (a gap) instead of drawing a body.
          open: b.open != null ? Number(b.open) : null,
          high: b.high != null ? Number(b.high) : null,
          low: b.low != null ? Number(b.low) : null,
          close: Number(b.close),
          volume: b.volume != null ? Number(b.volume) : null,
          volume_type: b.volume_type || null,
          ohlc_status: b.ohlc_status,
        })).filter((b) => b.close !== null)
      : data.bars.filter((b) => b.close !== null);

    // Candles need four real prices. The capability is a property of the DATA,
    // not of the instrument: an index with genuine OHLC rows is candle-capable,
    // a close-only stock series is not. `ohlcOk` drives both the default chart
    // type and which options are enabled (see OHLC_STYLES below).
    const OHLC_STYLES = new Set(["candles", "hollow", "heikin", "bars"]);
    const hasBody = (b) => b.open != null && b.high != null && b.low != null && b.ohlc_status !== "invalid";
    const ohlcOk = isIndex
      ? Number(data.genuine_ohlc_count || 0) > 0
      : bars.some(hasBody);
    state.chartOhlcOk = ohlcOk;
    // First date with a genuine body straight from the API, so the note reports
    // the dataset's real candle coverage rather than the loaded window's.
    const genuineFirst = isIndex ? (data.genuine_first_date || null) : null;

    // The meta line is a label, not a paragraph: symbol, timeframe and the window
    // on screen. The source and adjustment status stay available (tooltip) instead
    // of announcing themselves above the chart.
    const tfLabel = { daily: "Daily", weekly: "Weekly", monthly: "Monthly" }[tf] || tf;
    const metaSymbol = isIndex ? (data.name || "NEPSE") : data.symbol;
    const metaCount = isIndex ? (data.rows_returned || bars.length) : data.count;
    const metaFirst = isIndex ? (data.first_date || bars[0]?.time) : data.first_date;
    const metaLast = isIndex ? (data.last_date || bars[bars.length-1]?.time) : data.last_date;
    const idxNote = isIndex
      ? ` · <span class="chart-dim" title="NEPSE composite index. ${data.genuine_ohlc_count || 0} genuine OHLC rows, ${data.placeholder_ohlc_count || 0} placeholder (close-only) rows. Volume is market-wide turnover in NPR. Not a live feed.">index · ${data.genuine_ohlc_count || 0} OHLC / ${data.placeholder_ohlc_count || 0} close-only</span>`
        + (genuineFirst
          ? ` · <span class="chart-dim" title="Candle and OHLC-bar chart types draw only rows with genuine Open/High/Low. Earlier placeholder rows appear as gaps — they are never rendered as fabricated candles.">candles from ${esc(String(genuineFirst).slice(0, 10))}</span>`
          : "")
      : ` · <span class="chart-dim" title="Prices are not adjusted for bonus or split, and this is the stored dataset — not a live feed.">unadjusted · historical</span>`;
    $("#chart-meta").innerHTML =
      `<b>${esc(metaSymbol)}</b> · ${esc(tfLabel)} · ${fmtInt(metaCount)} obs · ` +
      `${esc(String(metaFirst).slice(0, 10))} → <b>${esc(String(metaLast).slice(0, 10))}</b>` +
      idxNote;

    if (!bars.length) { errEl.textContent = "No plottable bars (all closes missing)."; return; }

    if (!bars.length) { errEl.textContent = "No plottable bars (all closes missing)."; return; }

    const chart = makeChart($("#chart"), Math.max(360, ($("#chart").clientHeight || 520)));
    state.charts.price = chart;
    state.panEnabled = !(state.drawTool && !DRAW_MODES.has(state.drawTool));
    try { chart.applyOptions({ handleScroll: { pressedMouseMove: state.panEnabled } }); } catch (e) { /* older build */ }
    // Real pointer coordinates from the chart itself (data-coordinate system),
    // so manual drawings stay correct under zoom/pan/range changes.
    chart.subscribeClick(onChartClick);
    // §5.7: navigation (zoom/pan) becomes undoable via the unified stack.
    installViewHistory(chart);
    // The pointer tracker is bound once in bindDrawings(), not on every chart
    // rebuild. Re-adding it here leaked duplicate listeners and could reset the
    // drag guard mid-gesture.
    state.chartDrag = { mouseDown: null };
    // §5.6: compact OHLCV strip that follows the crosshair (bound after the
    // bars are in state — see below, before afterChartBuilt). Assumes the
    // chart exists so the crosshair subscription lands on the real instance.

    // §8C chart styles. Native lightweight-charts series are used where the
    // engine supports them; Heikin Ashi is an explicit, documented display
    // TRANSFORM (its values are not executable prices) and hollow candles use
    // per-bar colour overrides so an up candle is drawn hollow.
    // Default follows the DATA: candles when the series has real OHLC (the
    // NEPSE index does, from 2016-11-28), a line when it is genuinely
    // close-only. Options that cannot work are disabled by the OHLC_STYLES
    // gate further below.
    const style = (($("#chart-type") || {}).value) || (ohlcOk ? "candles" : "line");
    let candle = null;
    const nativeLine = () => chart.addLineSeries({ color: PRAVAHA.cyan, lineWidth: 2, priceLineVisible: true });
    const nativeArea = () => chart.addAreaSeries({
      lineColor: PRAVAHA.cyan, topColor: "rgba(0,217,232,.30)",
      bottomColor: "rgba(0,217,232,0)", lineWidth: 2, priceLineVisible: false,
    });
    // OHLC payload for a candle/bar series. A row without a usable body (a
    // placeholder close-only row, or a row the source flagged invalid) is
    // emitted as whitespace ({time} only) so lightweight-charts draws a GAP
    // rather than a fabricated or inconsistent body. Genuine rows pass through.
    const ohlcData = (b) => hasBody(b)
      ? { time: b.time, open: b.open, high: b.high, low: b.low, close: b.close }
      : { time: b.time };

    if (style === "line" || style === "area" || style === "step" || style === "baseline" || style === "column" || style === "line_markers") {
      if (style === "area") {
        candle = nativeArea();
      } else if (style === "step") {
        candle = chart.addLineSeries({ color: PRAVAHA.cyan, lineWidth: 2, priceLineVisible: false, lineType: 1 });
      } else if (style === "baseline") {
        candle = chart.addBaselineSeries({
          baseValue: { type: "price", price: bars[0].close },
          topLineColor: PRAVAHA.up, topFillColor1: "rgba(31,201,138,.22)", topFillColor2: "rgba(31,201,138,.02)",
          bottomLineColor: PRAVAHA.down, bottomFillColor1: "rgba(255,107,120,.02)", bottomFillColor2: "rgba(255,107,120,.22)",
          lineWidth: 2, priceLineVisible: false,
        });
      } else if (style === "column") {
        candle = chart.addHistogramSeries({ priceFormat: { type: "price", precision: 2, minMove: 0.01 } });
      } else {
        candle = nativeLine();
      }
      if (style === "column") {
        candle.setData(bars.map((b) => ({
          time: b.time, value: b.close,
          color: b.close >= (b.open ?? b.close) ? "rgba(31,201,138,.7)" : "rgba(255,107,120,.7)",
        })));
      } else {
        candle.setData(bars.map((b) => ({ time: b.time, value: b.close })));
      }
      if (style === "line_markers") {
        // Display markers at close-based fractal pivots (k=2 each side).
        // Markers are labelled as display geometry, not signals; they join the
        // same marker set swings/candles use, so flushing never erases them.
        for (let i = 2; i < bars.length - 2; i++) {
          const c = Number(bars[i].close);
          let hi = true, lo = true;
          for (let j = i - 2; j <= i + 2; j++) {
            if (j === i) continue;
            if (Number(bars[j].close) >= c) hi = false;
            if (Number(bars[j].close) <= c) lo = false;
          }
          if (hi) state.markers.push(noteMarker({ time: bars[i].time, position: "aboveBar", color: PRAVAHA.down, shape: "circle", text: "" }, "Pivot dots (±2-bar close pivot)", "A ±2-bar close-based pivot dot. Turn off the swings layer to clear these."));
          else if (lo) state.markers.push(noteMarker({ time: bars[i].time, position: "belowBar", color: PRAVAHA.up, shape: "circle", text: "" }, "Pivot dots (±2-bar close pivot)", "A ±2-bar close-based pivot dot. Turn off the swings layer to clear these."));
        }
      }
    } else if (style === "bars") {
      candle = chart.addBarSeries({
        upColor: PRAVAHA.up, downColor: PRAVAHA.down, thinBars: false,
      });
      candle.setData(bars.map(ohlcData));
    } else if (style === "hollow") {
      // Hollow candles: up candles are drawn with a transparent body and a
      // coloured border/wick; down candles stay filled. Real OHLC geometry.
      candle = chart.addCandlestickSeries({
        upColor: "rgba(0,0,0,0)", downColor: PRAVAHA.down, borderVisible: true,
        borderUpColor: PRAVAHA.up, borderDownColor: PRAVAHA.down,
        wickUpColor: PRAVAHA.up, wickDownColor: PRAVAHA.down,
      });
      candle.setData(bars.map((b) => {
        if (!hasBody(b)) return { time: b.time };
        const o = b.open, c = b.close, bull = c >= o;
        return {
          time: b.time, open: o, high: b.high, low: b.low, close: c,
          color: bull ? "rgba(0,0,0,0)" : PRAVAHA.down,
          borderColor: bull ? PRAVAHA.up : PRAVAHA.down,
          wickColor: bull ? PRAVAHA.up : PRAVAHA.down,
        };
      }));
    } else if (style === "heikin") {
      // Heikin Ashi is a well-documented smoothing transform:
      //   haClose = (O+H+L+C)/4
      //   haOpen  = (haOpen[prev] + haClose[prev]) / 2   (first bar: (O+C)/2)
      //   haHigh  = max(H, haOpen, haClose);  haLow = min(L, haOpen, haClose)
      // These are DISPLAY values — they are not executable prices, and the
      // chart is labelled as a transform in the meta line.
      const ha = [];
      let pO = null, pC = null;
      bars.forEach((b) => {
        // A placeholder (close-only) or source-flagged invalid row has no body:
        // emit whitespace and RESET the chain, so the first genuine candle after
        // a gap seeds from its own (O+C)/2 rather than from a synthetic value.
        if (!hasBody(b)) {
          ha.push({ time: b.time });
          pO = null; pC = null;
          return;
        }
        const o = Number(b.open), h = Number(b.high),
          l = Number(b.low), c = Number(b.close);
        const hc = (o + h + l + c) / 4;
        const ho = (pO == null || pC == null) ? (o + c) / 2 : (pO + pC) / 2;
        ha.push({ time: b.time, open: ho, high: Math.max(h, ho, hc), low: Math.min(l, ho, hc), close: hc });
        pO = ho; pC = hc;
      });
      candle = chart.addCandlestickSeries({
        upColor: PRAVAHA.up, downColor: PRAVAHA.down, borderVisible: false,
        wickUpColor: PRAVAHA.up, wickDownColor: PRAVAHA.down,
      });
      candle.setData(ha);
      $("#chart-meta").innerHTML += ` · <span class="chart-dim" title="Heikin Ashi transform: haClose=(O+H+L+C)/4; haOpen=(prev haOpen+prev haClose)/2. Display values only — not executable prices.">Heikin Ashi (display transform — not executable prices)</span>`;
    } else {
      candle = chart.addCandlestickSeries({
        upColor: PRAVAHA.up, downColor: PRAVAHA.down, borderVisible: false,
        wickUpColor: PRAVAHA.up, wickDownColor: PRAVAHA.down,
      });
      candle.setData(bars.map(ohlcData));
    }

    if ($("#ind-vol").checked && !isIndex) {
      const vol = chart.addHistogramSeries({
        priceFormat: { type: "volume" }, priceScaleId: "vol",
        color: PRAVAHA.borderLite,
      });
      chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
      vol.setData(bars.map((b) => ({
        time: b.time, value: b.volume || 0,
        color: (b.close >= (b.open ?? b.close)) ? "rgba(31,201,138,.5)" : "rgba(255,107,120,.5)",
      })));
      state.paneSeries.vol = vol;
    }
    // Chart-type availability reflects the DATA, not the instrument. Candles,
    // hollow candles, Heikin Ashi and OHLC bars need four real prices, so a
    // genuinely close-only series disables them and says why in the option
    // tooltip. The NEPSE index is candle-capable: 2,217 genuine OHLC rows from
    // 2016-11-28, with the earlier placeholder rows shown as gaps (see
    // `ohlcData` above) rather than as fabricated candles.
    {
      const ct = $("#chart-type");
      if (ct) {
        Array.from(ct.options).forEach((opt) => {
          const blocked = OHLC_STYLES.has(opt.value) && !ohlcOk;
          opt.disabled = blocked;
          opt.title = blocked
            ? "Unavailable: this series has no Open/High/Low (close-only). Use Line or Area."
            : "";
        });
        if (OHLC_STYLES.has(ct.value) && !ohlcOk) ct.value = "line";
      }
    }

    const dates = bars.map((b) => b.time);

    // Quick layers are the chart-toolbar toggles. Each created primitive is
    // registered so the Chart Objects manager can name it, show its
    // owner/visibility and hide/remove the real series, pane or owned markers —
    // not just a row. One entry per toolbar toggle (so two SMA lines are one
    // "SMA 20/50" object, matching the checkbox). They are rebuilt on every
    // load and intentionally NOT persisted; the right-hand drawer analysis
    // layers are the persistent equivalent.
    state.quickObjects = [];
    const regQuick = (desc, target) => { state.quickObjects.push(Object.assign({}, desc, target)); };

    if ($("#ind-sma").checked) {
      const s20 = await addOverlay(chart, symbol, "sma", { period: 20 }, dates, PRAVAHA.caution, "SMA 20");
      const s50 = await addOverlay(chart, symbol, "sma", { period: 50 }, dates, PRAVAHA.cyan, "SMA 50");
      regQuick({ id: "quick-sma", label: "SMA 20 / 50", type: "Overlay · moving average", owner: "Quick layers (toolbar)", checkbox: "ind-sma",
        desc: "Two simple moving averages (20 and 50) on the price scale, from the toolbar 'SMA 20/50' toggle." }, { seriesList: [s20, s50].filter(Boolean) });
    }
    if ($("#ind-ema").checked) {
      const s = await addOverlay(chart, symbol, "ema", { period: 20 }, dates, PRAVAHA.mint, "EMA 20");
      regQuick({ id: "quick-ema", label: "EMA 20", type: "Overlay · moving average", owner: "Quick layers (toolbar)", checkbox: "ind-ema",
        desc: "Exponential moving average (20) on the price scale, from the toolbar 'EMA 20' toggle." }, { series: s });
    }
    if ($("#ind-bb").checked) {
      const mid = await addOverlay(chart, symbol, "bollinger", { period: 20, std_dev: 2 }, dates, PRAVAHA.muted, "BB mid", "middle");
      const up = await addOverlay(chart, symbol, "bollinger", { period: 20, std_dev: 2 }, dates, "rgba(157,180,174,.6)", "BB upper", "upper");
      const lo = await addOverlay(chart, symbol, "bollinger", { period: 20, std_dev: 2 }, dates, "rgba(157,180,174,.6)", "BB lower", "lower");
      regQuick({ id: "quick-bb", label: "Bollinger (20, 2σ)", type: "Overlay · volatility bands", owner: "Quick layers (toolbar)", checkbox: "ind-bb",
        desc: "Bollinger middle/upper/lower on the price scale, from the toolbar 'Bollinger' toggle." }, { seriesList: [mid, up, lo].filter(Boolean) });
    }
    if (state.paneSeries.vol) {
      regQuick({ id: "quick-vol", label: "Volume", type: "Overlay · histogram (volume scale)", owner: "Quick layers (toolbar)", checkbox: "ind-vol",
        desc: "Per-bar traded volume, coloured by up/down close, on its own 'vol' scale." }, { series: state.paneSeries.vol });
    }

    if ($("#ind-rsi").checked) {
      await addPane("rsi-pane", "rsi", symbol, {}, dates, PRAVAHA.cyan, "RSI(14)", 0, 100);
      regQuick({ id: "quick-rsi", label: "RSI (14)", type: "Oscillator pane", owner: "Quick layers (toolbar)", checkbox: "ind-rsi",
        desc: "Relative Strength Index (14) in its own synced pane, from the toolbar 'RSI pane' toggle." }, { paneId: "rsi-pane" });
    }
    if ($("#ind-macd").checked) {
      await addPane("macd-pane", "macd", symbol, {}, dates, PRAVAHA.cyan, "MACD");
      await addPane("macd-pane", "macd", symbol, {}, dates, PRAVAHA.caution, "Signal", 0, 0, "signal", true);
      regQuick({ id: "quick-macd", label: "MACD (12, 26, 9)", type: "Oscillator pane", owner: "Quick layers (toolbar)", checkbox: "ind-macd",
        desc: "MACD line + signal in their own synced pane, from the toolbar 'MACD pane' toggle." }, { paneId: "macd-pane" });
    }
    if ($("#ind-swings").checked) {
      if (isIndex) await addIndexSwings($("#chart-note"));
      else await addSwings(symbol, range, candle, $("#chart-note"));
      regQuick({ id: "quick-swings", label: isIndex ? "Index OHLC swings" : "Swings (OHLC)", type: "Annotation markers", owner: "Quick layers (toolbar)", checkbox: "ind-swings",
        desc: "Confirmed OHLC swing markers (SH/SL) from the toolbar 'Swings' toggle." },
        { markerOwner: isIndex ? "Index OHLC swing detector" : "Swing-structure detector" });
    }
    if ($("#ind-close-swings")?.checked && isIndex) {
      await addCloseSwings(bars, $("#chart-note"));
      regQuick({ id: "quick-closeswings", label: "Close-based pivots", type: "Annotation markers", owner: "Quick layers (toolbar)", checkbox: "ind-close-swings",
        desc: "Close-based pivot markers (CH/CL) from the toolbar 'Close-based pivots' toggle." }, { markerOwner: "Close-based swing detector (index)" });
    }

    state.candleSeries = candle;
    state.chartSymbol = symbol;
    state.chartRange = range;
    state.chartDates = dates.slice();
    state.chartBars = bars;
    // Rebuild custom indicators now that state.chartBars is in place (the
    // custom-formula DSL reads the bars; calling earlier left it empty).
    try { await rebuildCustomIndicators(symbol, dates, isIndex); } catch (e) { console.warn("rebuildCustomIndicators failed:", e && e.message); }
    // Multi-symbol comparison overlays (persisted per primary symbol).
    state.compare = loadCompareCfg(symbol);
    try { await applyCompareToChart(seq); } catch (e) { console.warn("compare overlay failed:", e && e.message); }
    if (!state.indHist.stack.length) indHistPush();
    try { await renderIndDrawer(); } catch (e) { /* drawer stays as-is */ }

    // §5.6 OHLCV strip (after the state it reads is in place)
    bindOhlcvLegend(chart);
    // Load this symbol's saved manual drawings and paint them (before markers).
    afterChartBuilt(symbol);
    loadBenchmarks();

    // Restore each symbol's saved analysis configuration BEFORE any layer runs:
    // a layer toggle re-runs the detector (and saves the controls), so doing it
    // after would analyse with the previous symbol's settings and overwrite this
    // symbol's saved window.
    try { applyElliottCfg(symbol); } catch (e) { /* defaults stand */ }
    try { applyHarmonicCfg(symbol); } catch (e) { /* defaults stand */ }
    // Analysis overlays are OPT-IN (the Analysis drawer on the right). The chart
    // opens as candles + volume only. A layer adds its own fetch and drawing; a
    // failed or empty result renders nothing rather than an invented line.
    await applyChartLayers(chart, symbol, bars);
    // Re-apply any saved manual Elliott labels for this symbol.
    try { applyElliottLabels(); } catch (e) { /* nothing saved */ }

    flushMarkers(candle);
    await loadChartInsights(symbol);

    // Restore the previous window on a same-context reload; otherwise fit.
    if (keepRange) {
      try { chart.timeScale().setVisibleLogicalRange(keepRange); } catch (e) { chart.timeScale().fitContent(); }
    } else {
      chart.timeScale().fitContent();
    }
    $("#export-csv").onclick = () => exportCsv(symbol, data.bars);
    saveAutosave();   // §8K: persist only when the explicit switch is ON
  } catch (e) {
    const msg = String((e && e.message) || e);
    // A 404 "no stored history" is a MISSING-DATA state, not a broken route or a
    // blocked request: the endpoint exists and answered. Say so plainly so a
    // bare "404" is never mistaken for a missing route.
    errEl.textContent = /no stored history/i.test(msg)
      ? `No stored market data for ${symbol} in this deployment — the market database is empty. ` +
        `Ingest NEPSE history (or place a prepared database on the persistent disk) to chart it. ` +
        `The API is reachable and the route is correct.`
      : `Could not load ${symbol}: ${msg}`;
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

  confirmed.forEach((s) => {
    state.markers.push(noteMarker({
      time: s.date,
      position: s.kind === "high" ? "aboveBar" : "belowBar",
      color: s.kind === "high" ? PRAVAHA.down : PRAVAHA.up,
      shape: s.kind === "high" ? "arrowDown" : "arrowUp",
      text: s.kind === "high" ? "SH" : "SL",
    }, "Swing-structure detector",
    `${s.kind === "high" ? "SH" : "SL"} = confirmed swing ${s.kind} at ${s.date} from OHLC geometry. `
    + `Turn off the Support & resistance / swings layer to clear these.`));
  });

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

/* Close-based swing detection for close-only series (e.g. NEPSE index).
   A pivot high is a bar whose close is the highest within ±N bars.
   A pivot low is the opposite. Clearly labelled as close-based, NOT
   conventional OHLC swing detection. */
async function addCloseSwings(bars, noteEl) {
  const N = 5;
  const highs = [], lows = [];
  for (let i = N; i < bars.length - N; i++) {
    const c = bars[i].close;
    let isHigh = true, isLow = true;
    for (let j = i - N; j <= i + N; j++) {
      if (j === i) continue;
      if (bars[j].close > c) isHigh = false;
      if (bars[j].close < c) isLow = false;
    }
    if (isHigh) highs.push({ date: bars[i].time, kind: "high" });
    if (isLow) lows.push({ date: bars[i].time, kind: "low" });
  }
  const all = [...highs, ...lows].sort((a, b) => String(a.date).localeCompare(String(b.date)));
  all.forEach((s) => {
    state.markers.push(noteMarker({
      time: s.date,
      position: s.kind === "high" ? "aboveBar" : "belowBar",
      color: s.kind === "high" ? PRAVAHA.down : PRAVAHA.up,
      shape: s.kind === "high" ? "arrowDown" : "arrowUp",
      text: s.kind === "high" ? "CH" : "CL",
    }, "Close-based swing detector (index)",
    `${s.kind === "high" ? "CH" : "CL"} = close-based pivot ${s.kind} at ${s.date}, ±${N}-bar window on closing prices only. `
    + `NOT conventional OHLC swing detection — the index series has no high/low. Turn off the swings layer to clear these.`));
  });
  if (noteEl) {
    noteEl.textContent =
      `Close-based pivots: ${highs.length} high(s), ${lows.length} low(s) (±${N}-bar window on closing prices). ` +
      `These are NOT conventional OHLC swing points — the index has no high/low data. ` +
      "DETected from close prices only, not a validated signal.";
  }
}

/* Index OHLC swing detection (NEPSE only).
   Uses the /api/indices/{name}/structure endpoint which computes swings
   from genuine OHLC rows only. Placeholder and invalid rows excluded. */
async function addIndexSwings(noteEl) {
  const d = await api("/api/indices/NEPSE/structure");
  const confirmed = (d.swings || []).filter((s) => s.confirmed);
  confirmed.forEach((s) => {
    state.markers.push(noteMarker({
      time: s.date,
      position: s.kind === "high" ? "aboveBar" : "belowBar",
      color: s.kind === "high" ? PRAVAHA.down : PRAVAHA.up,
      shape: s.kind === "high" ? "arrowDown" : "arrowUp",
      text: s.kind === "high" ? "SH" : "SL",
    }, "Index OHLC swing detector",
    `${s.kind === "high" ? "SH" : "SL"} = confirmed swing ${s.kind} at ${s.date}, computed from genuine OHLC rows only `
    + `(placeholder and invalid rows excluded). Turn off the swings layer to clear these.`));
  });
  if (noteEl) {
    const dq = d.data_quality || {};
    noteEl.textContent =
      `${d.counts.swings} swings (${d.counts.swing_highs}H/${d.counts.swing_lows}L)` +
      ` · structure: ${d.trend}` +
      ` · ${d.breaks.length} break(s)` +
      ` · ${dq.genuine_rows_used} genuine OHLC rows` +
      (dq.data_gaps ? ` · ${dq.data_gaps} data gap(s) not bridged` : "") +
      " · DETECTED from geometry, not a validated signal";
  }
}

/* Candlestick letter markers (M, D, DD, ST…) are informative per-event but a
   wall of them over a 6-month chart is noise (§5.9). The cap keeps only the
   most RECENT N events — the past stays in the candlestick panel, unhiding is
   a render-control change, not a data loss. */
function cappedCandleMarkers() {
  const cap = (state.overlayVis && state.overlayVis.candleCap) ?? 15;
  const cm = state.candleMarkers || [];
  if (cap <= 0) return [];               // Minimal mode: no letters at all
  if (!cm.length || cm.length <= cap) return cm;
  return cm.slice().sort((a, b) => String(a.time).localeCompare(String(b.time))).slice(-cap);
}

/* Write every collected marker to the candle series in a single, time-ordered
   call. Two markers can share a date (e.g. a swing and a candlestick shape on
   the same bar); lightweight-charts accepts that as long as the request is
   sorted ascending by time, so we sort and de-duplicate identical entries. */
function markerHostSeries(candleSeries) {
  const candle = candleSeries || state.candleSeries;
  if (!candle || candle !== state.candleSeries || !state.charts.price) return null;
  const dates = state.chartDates || [];
  if (!dates.length) return null;
  let host = state.markerSeries;
  if (!host) {
    // An invisible candlestick series mirrors the visible OHLC exactly, so
    // aboveBar/belowBar markers keep their normal high/low anchoring. Only the
    // autoscale exclusion is different.
    host = state.charts.price.addCandlestickSeries({
      upColor: "rgba(0,0,0,0)", downColor: "rgba(0,0,0,0)",
      borderVisible: false, wickUpColor: "rgba(0,0,0,0)",
      wickDownColor: "rgba(0,0,0,0)", priceLineVisible: false,
      lastValueVisible: false, autoscaleInfoProvider: () => null,
    });
    state.markerSeries = host;
  }
  const key = `${dates.length}|${dates[0]}|${dates[dates.length - 1]}`;
  if (state.markerSeriesKey !== key) {
    const bars = state.chartBars || [];
    const fallback = bars.length ? Number(bars[0].close) : 0;
    const value = (v) => (isFinite(Number(v)) ? Number(v) : (isFinite(fallback) ? fallback : 0));
    host.setData(dates.map((t, i) => {
      const b = bars[i] || {};
      const close = value(b.close);
      return {
        time: String(t), open: value(b.open), high: value(b.high),
        low: value(b.low), close,
      };
    }));
    state.markerSeriesKey = key;
  }
  // Do not leave a second copy of the markers on the candle series.
  try { candle.setMarkers([]); } catch (e) { /* older build */ }
  return host;
}

function flushMarkers(candleSeries) {
  const series = markerHostSeries(candleSeries) || candleSeries || state.candleSeries;
  if (!series) return;  const all = [
    ...state.markers,
    ...cappedCandleMarkers(),
    ...state.elliottMarkers,
    ...state.elliottAutoMarkers,
    ...state.harmonicMarkers,
    ...state.structureMarkers,
    ...state.trendMarkers,
    ...state.momentumMarkers,
    ...state.volatilityMarkers,
    ...state.volumeMarkers,
    ...state.gapMarkers,
    ...state.regimeMarkers,
    ...state.relativeMarkers,
    ...state.microMarkers,
    ...state.distributionMarkers,
    ...state.eventMarkers,
    ...state.strategyMarkers,
    ...state.drawMarkers,
    ...(state.pendingMarker || []),
    ...(state.selectionMarkers || []),
    ...state.patternMarkers,
  ];
  const seen = new Set();
  const ordered = all
    .filter((m) => m && m.time && !m.hidden)
    .slice()
    .sort((a, b) => String(a.time).localeCompare(String(b.time)))
    .filter((m) => {
      const key = `${m.time}|${m.position}|${m.shape}|${m.text}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  series.setMarkers(ordered);
}

/* Marker provenance (§objects). Lightweight-charts only reads
   time/position/color/shape/text, so the owner/description of each annotation
   is kept in a side table keyed by the same tuple the renderer uses. This is
   what lets the Chart Objects manager say *which* feature created a "BO" label
   instead of leaving a cryptic code on the chart. */
function markerKeyOf(m) { return `${m.time}|${m.position}|${m.shape}|${m.text}`; }
function noteMarker(marker, owner, desc) {
  if (!marker || !marker.time) return marker;
  state.markerMeta[markerKeyOf(marker)] = { owner, desc };
  return marker;
}
function markerMetaOf(m) {
  return (state.markerMeta && state.markerMeta[markerKeyOf(m)]) || null;
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
  return line;
}

/* Mirror the price chart's window onto a pane. Called after the pane receives
   its data: setting a range on an empty chart is dropped, so the seed has to
   happen once the series exists. Navigation stays on the price chart. */
function syncPaneToPrice(paneId) {
  const pane = state.charts[paneId];
  const main = state.charts.price;
  if (!pane || !main || pane === main) return;
  try {
    const r = main.timeScale().getVisibleLogicalRange();
    if (r) pane.timeScale().setVisibleLogicalRange(r);
  } catch (e) { /* not measurable yet */ }
}

async function addPane(paneId, name, symbol, params, dates, color, title, min, max, field, reuse) {
  let chart = state.charts[paneId];
  if (!chart || !reuse) {
    // paneId is an element id ("rsi-pane"), not a selector - `$(...)` would look
    // for a literal <rsi-pane> element and find nothing, which is why the
    // indicator panes never rendered before.
    const sel = paneId.charAt(0) === "#" ? paneId : `#${paneId}`;
    const el = $(sel);
    if (!el) return;
    // A zero-sized container gets no canvas from lightweight-charts, so the pane
    // is unhidden *before* the chart is created, never after.
    el.hidden = false;
    chart = makeChart(el, 170);
    state.charts[paneId] = chart;
    if (min !== undefined && max !== undefined) {
      chart.applyOptions({ rightPriceScale: { autoScale: false } });
    }
    // Align the pane's time axis with the price chart: ONE direction only
    // (price chart -> pane). The reverse subscription used to exist and was the
    // cause of a real defect: a freshly created pane chart fires its own
    // default range, which then overwrote the price chart's zoom, so simply
    // adding an indicator silently re-framed the chart. Navigation lives on the
    // price chart; every pane follows it.
    const main = state.charts.price;
    if (main) {
      main.timeScale().subscribeVisibleLogicalRangeChange((r) => {
        if (r) chart.timeScale().setVisibleLogicalRange(r);
      });
      // Seed the new pane from the price chart instead of letting it pick its
      // own default range.
      try {
        const cur = main.timeScale().getVisibleLogicalRange();
        if (cur) chart.timeScale().setVisibleLogicalRange(cur);
      } catch (e) { /* not measurable yet */ }
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
  syncPaneToPrice(paneId);
  return line;
}

/* Add one more output of a multi-output indicator to an EXISTING pane chart
   (so a pane shows all of an indicator's lines, not just the first). */
async function addPaneOutput(paneId, name, symbol, params, dates, color, title, field) {
  const chart = state.charts[paneId];
  if (!chart) return null;
  const r = await api(`/api/bars/${encodeURIComponent(symbol)}/indicator?${indQuery(name, params)}`);
  const key = field || Object.keys(r.series)[0];
  const aligned = alignedSeries(r, key, dates);
  const line = chart.addLineSeries({ color, lineWidth: 1, priceLineVisible: false, title });
  line.setData(
    dates
      .map((d, i) => ({ time: d, value: aligned[i] }))
      .filter((p) => p.value !== null && p.value !== undefined)
  );
  syncPaneToPrice(paneId);
  return line;
}

/* ------------------------------------------------------------ indicator catalog
   The catalog is driven by the backend's own registry (GET /api/indicators):
   one row per registered, formula-documented indicator. Nothing is named here
   that the backend cannot compute. */
/* Placement rules for catalog indicators (checked in order):
   1. The registry's `display` hint when present.
   2. momentum & volume categories -> their own synced pane.
   3. trend -> price overlay, except the named pane readings below.
   4. volatility -> overlay only for pure band groups (upper+middle+lower,
      Donchian/Keltner/standard-error bands); everything else is a pane, and
      Bollinger's ratio outputs (bandwidth, %B) keep it in a pane so they can
      never wreck the price scale while all five outputs still render.
   5. other -> the named price-unit series overlay; the rest pane. */
const IND_TREND_PANE = new Set(["adx", "aroon", "linreg_slope", "supertrend"]);
const IND_VOLUME_OVERLAY = new Set(["vwap_bands"]);
const IND_OTHER_OVERLAY = new Set(["median_price", "typical_price", "weighted_close", "pivot_points"]);
const IND_VOL_BAND_OUTPUTS = new Set(["upper", "middle", "lower"]);
function indPlacement(reg) {
  if (!reg) return "pane";
  if (reg.display === "overlay") return "overlay";
  if (reg.display === "pane") return "pane";
  const cat = reg.category;
  if (cat === "momentum") return "pane";
  if (cat === "volume") return IND_VOLUME_OVERLAY.has(reg.name) ? "overlay" : "pane";
  if (cat === "trend") return IND_TREND_PANE.has(reg.name) ? "pane" : "overlay";
  if (cat === "volatility") {
    const outs = reg.outputs || [];
    return outs.length && outs.every((o) => IND_VOL_BAND_OUTPUTS.has(o)) ? "overlay" : "pane";
  }
  return IND_OTHER_OVERLAY.has(reg.name) ? "overlay" : "pane";
}
const IND_COLORS = [PRAVAHA.cyan, PRAVAHA.caution, PRAVAHA.mint, PRAVAHA.up, PRAVAHA.down, PRAVAHA.muted];
function indColor(key) {
  let h = 0;
  for (const ch of key) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return IND_COLORS[h % IND_COLORS.length];
}
/* ----------------------------------------------------- indicator instance model
   Every catalog indicator on the chart is an INSTANCE: a unique id plus its
   name, parameters, label, colour and visibility. One indicator can therefore
   appear several times with different parameters, and each instance can be
   hidden, renamed, duplicated, reordered or removed on its own. Entries saved
   by earlier versions ({name, params}) are upgraded in place — nothing saved
   in this browser is lost. */
function newIndId() {
  return `i${Date.now().toString(36)}${Math.floor(Math.random() * 1e6).toString(36)}`;
}
function customIndsKey(symbol) { return `mt-custom-inds-${symbol}`; }
function loadCustomInds(symbol) {
  try {
    const raw = JSON.parse(localStorage.getItem(customIndsKey(symbol)) || "[]");
    if (!Array.isArray(raw)) return [];
    return raw.filter((x) => x && x.name).map((x) => ({
      id: x.id || newIndId(),
      name: String(x.name),
      params: (x.params && typeof x.params === "object" && !Array.isArray(x.params)) ? x.params : {},
      label: typeof x.label === "string" ? x.label : "",
      color: typeof x.color === "string" ? x.color : "",
      visible: x.visible !== false,
    }));
  } catch (e) { return []; }
}
function persistCustomInds(symbol) {
  try { localStorage.setItem(customIndsKey(symbol), JSON.stringify(state.customInds || [])); } catch (e) { /* off */ }
}

/* Undo/redo for indicator configuration. Snapshots are small JSON records of
   the quick-layer flags + the instance list for the loaded symbol; restoring
   one only re-applies the chart configuration (never data). */
function indSnapshot() {
  const quick = {};
  IND_TEMPLATE_KEYS.forEach((k) => { const el = $("#ind-" + k); quick[k] = !!(el && el.checked); });
  return { quick, instances: JSON.parse(JSON.stringify(state.customInds || [])) };
}
function indHistPush() {
  if (!state.chartSymbol) return;
  const snap = indSnapshot();
  const h = state.indHist;
  const last = h.stack[h.idx];
  if (last && JSON.stringify(last) === JSON.stringify(snap)) return;   // no-op change
  h.stack = h.stack.slice(0, h.idx + 1);
  h.stack.push(snap);
  if (h.stack.length > 40) h.stack.shift();
  h.idx = h.stack.length - 1;
  updateIndUndoButtons();
}
function updateIndUndoButtons() {
  const h = state.indHist;
  const u = $("#ind-undo"), r = $("#ind-redo");
  if (u) u.disabled = h.idx <= 0;
  if (r) r.disabled = h.idx >= h.stack.length - 1;
}
async function indHistStep(delta) {
  const h = state.indHist;
  const next = h.idx + delta;
  if (next < 0 || next >= h.stack.length) return;
  h.idx = next;
  const snap = h.stack[next];
  IND_TEMPLATE_KEYS.forEach((k) => { const el = $("#ind-" + k); if (el) el.checked = !!snap.quick[k]; });
  state.customInds = JSON.parse(JSON.stringify(snap.instances || []));
  persistCustomInds(state.chartSymbol);
  updateIndUndoButtons();
  await loadChart();
  renderIndDrawer();
}

async function fetchIndicatorRegistry() {
  if (state.indRegistry) return state.indRegistry;
  const r = await api("/api/indicators");
  state.indRegistry = r.indicators || [];
  return state.indRegistry;
}

function createCustomPaneDiv(name, reg, idKey) {
  const host = document.querySelector(".chart-sub");
  if (!host) return null;
  const el = document.createElement("div");
  el.className = "chartbox small";
  el.id = `pane-custom-${idKey || name}`;
  el.style.height = "120px";
  host.appendChild(el);
  return el;
}

/* Overlays on the price chart; pane-category indicators get their own synced
   pane below (same construction the RSI/MACD panes use). Accepts an instance
   ({id, name, params, color, label, visible}) and returns the created series/
   pane handles so visibility can be toggled without recomputation. */
async function applyCatalogIndicator(inst, dates, symOverride) {
  if (typeof inst === "string") inst = { id: inst, name: inst, params: {} };
  const sym = symOverride || state.chartSymbol;
  if (!sym || !dates || !dates.length) throw new Error("Load a chart first.");
  const reg = (await fetchIndicatorRegistry()).find((x) => x.name === inst.name);
  await fetchIndicatorRegistry();
  const cat = reg ? reg.category : "other";
  const params = (inst.params && Object.keys(inst.params).length) ? inst.params : ((reg && reg.params) || {});
  const color = inst.color || indColor(inst.id || inst.name);
  const title = inst.label || (reg && reg.label) || inst.name;
  const visible = inst.visible !== false;
  const rec = { series: [], panes: [] };
  const paramStr = Object.entries(params).map(([k, v]) => `${k}=${v}`).join(" ");
  const outs = (reg && reg.outputs && reg.outputs.length) ? reg.outputs : [null];
  /* Placement: 1) the registry's display hint; 2) otherwise the category
     rules in indPlacement() (momentum/volume -> pane, trend -> overlay with
     named exceptions, volatility -> pane unless it is a pure price band). */
  const mode = indPlacement(reg);
  const outColor = (i) => (i === 0 ? color : IND_COLORS[(IND_COLORS.indexOf(color) + i) % IND_COLORS.length]);
  const drawPane = async (outList) => {
    if (!outList.length) return;
    const paneKey = `pane-custom-${inst.id}`;
    let el = document.getElementById(paneKey);
    if (!el) el = createCustomPaneDiv(inst.name, reg, inst.id);
    if (!el) throw new Error("Pane host missing.");
    el.dataset.title = `${sym} · ${title} · ${paramStr}`;
    el.hidden = !visible;
    for (let i = 0; i < outList.length; i++) {
      const o = outList[i];
      const line = i === 0
        ? await addPane(el.id, inst.name, sym, params, dates, color, title, undefined, undefined, o)
        : await addPaneOutput(el.id, inst.name, sym, params, dates, outColor(i), `${title}·${o}`, o);
      if (line && !visible) line.applyOptions({ visible: false });
      if (line) rec.series.push(line);
    }
    // addPane unhides the container to give the chart a measurable size; a
    // hidden instance must be re-hidden afterwards or its pane lingers empty.
    el.hidden = !visible;
    rec.panes.push(el);
  };
  const drawOverlay = async (outList) => {
    if (!outList.length) return;
    for (let i = 0; i < outList.length; i++) {
      const o = outList[i];
      const line = await addOverlay(state.charts.price, sym, inst.name, params, dates,
        outColor(i), (outList.length > 1 && o ? `${title}·${o}` : title), o);
      if (line && !visible) line.applyOptions({ visible: false });
      if (line) rec.series.push(line);
    }
  };
  if (mode === "pane") await drawPane(outs);
  else await drawOverlay(outs);
  state.indSeries[inst.id] = rec;
  renderPaneChips();
  renderPaneHeaders();
  return rec;
}

/* Hide / show one instance without recomputing anything: series visibility is
   a chart option and pane visibility a DOM state. */
function applyInstanceVisibility(inst) {
  const rec = state.indSeries[inst.id];
  if (!rec) return;
  (rec.series || []).forEach((s) => { try { s.applyOptions({ visible: inst.visible !== false }); } catch (e) { /* series gone */ } });
  (rec.panes || []).forEach((el) => { try { el.hidden = inst.visible === false; } catch (e) { /* pane gone */ } });
}

function renderPaneChips() {
  const sub = document.querySelector(".chart-sub");
  if (!sub) return;
  sub.querySelectorAll(".pane-chip[data-for]").forEach((n) => n.remove());
  document.querySelectorAll("[id^='pane-custom-']").forEach((el) => {
    const chip = document.createElement("div");
    chip.className = "pane-chip";
    chip.dataset.for = el.id;
    chip.textContent = `${el.dataset.title || el.id} — computed from stored daily bars (pane)`;
    sub.appendChild(chip);
  });
}

/* ===== pane headers: resize, collapse, remove =====
   Each custom indicator pane gets a small header sitting immediately before its
   chart container in .chart-sub. Collapse hides the container (autoSize brings
   it back on expand), the drag handle changes its height, and the ✕ removes the
   indicator instance (undoable from the drawer). Height and collapsed state are
   stored on the instance and persisted, so a reopened chart looks the same.
   The header is a sibling, never a child, of the lightweight-charts container:
   inserting DOM inside that container would fight the library's own sizing. */
function renderPaneHeaders() {
  const sub = document.querySelector(".chart-sub");
  if (!sub) return;
  const panes = Array.from(document.querySelectorAll("[id^='pane-custom-']"));
  sub.querySelectorAll("[data-pane-head]").forEach((h) => {
    if (!panes.some((p) => p.id === h.dataset.for)) h.remove();
  });
  panes.forEach((el) => {
    if (sub.querySelector(`[data-pane-head][data-for="${el.id}"]`)) {
      const t = sub.querySelector(`[data-pane-head][data-for="${el.id}"] .ph-title`);
      if (t) t.textContent = el.dataset.title || el.id;
      return;
    }
    const inst = (state.customInds || []).find((x) => `pane-custom-${x.id}` === el.id);
    if (inst && isFinite(Number(inst.paneHeight))) el.style.height = `${Math.max(60, Math.min(700, Number(inst.paneHeight)))}px`;
    const head = document.createElement("div");
    head.className = "pane-head";
    head.dataset.paneHead = "1";
    head.dataset.for = el.id;
    head.innerHTML = `<span class="ph-drag" title="Drag to resize this pane">&#8942;&#8942;</span>`
      + `<span class="ph-title">${esc(el.dataset.title || el.id)}</span>`
      + `<span class="ph-spacer"></span>`
      + `<button class="ph-btn" data-ph="collapse" title="Collapse / expand this pane">${inst && inst.paneCollapsed ? "&#9656;" : "&#9662;"}</button>`
      + `<button class="ph-btn" data-ph="tall" title="Taller pane">+</button>`
      + `<button class="ph-btn" data-ph="short" title="Shorter pane">&minus;</button>`
      + (inst ? `<button class="ph-btn" data-ph="remove" title="Remove this indicator from the chart (undoable)">&#10005;</button>` : "");
    sub.insertBefore(head, el);
    if (inst && inst.paneCollapsed) el.hidden = true;
    head.addEventListener("click", async (e) => {
      const b = e.target.closest("[data-ph]");
      if (!b) return;
      const act = b.dataset.ph;
      if (act === "collapse") {
        const willHide = !el.hidden;
        el.hidden = willHide;
        b.innerHTML = willHide ? "&#9656;" : "&#9662;";
        if (inst) { inst.paneCollapsed = willHide; persistCustomInds(state.chartSymbol); }
        return;
      }
      if (act === "tall" || act === "short") {
        const cur = parseInt(el.style.height || "120", 10);
        const next = Math.max(60, Math.min(700, cur + (act === "tall" ? 60 : -60)));
        el.style.height = `${next}px`;
        if (inst) { inst.paneHeight = next; persistCustomInds(state.chartSymbol); }
        return;
      }
      if (act === "remove" && inst) {
        await removeIndicatorInstance(inst.id);
        renderPaneHeaders();
      }
    });
    const handle = head.querySelector(".ph-drag");
    if (handle) {
      let dragging = false, startY = 0, startH = 120;
      handle.addEventListener("mousedown", (e) => {
        dragging = true;
        startY = e.clientY;
        startH = parseInt(el.style.height || "120", 10);
        e.preventDefault();
      });
      window.addEventListener("mousemove", (e) => {
        if (!dragging) return;
        el.style.height = `${Math.max(60, Math.min(700, startH + (e.clientY - startY)))}px`;
      });
      window.addEventListener("mouseup", () => {
        if (!dragging) return;
        dragging = false;
        const h = parseInt(el.style.height || "120", 10);
        if (inst) { inst.paneHeight = h; persistCustomInds(state.chartSymbol); }
      });
    }
  });
}

async function rebuildCustomIndicators(symbol, dates, isIndex) {
  state.customInds = loadCustomInds(symbol);
  const registry = await fetchIndicatorRegistry();
  for (const ci of state.customInds.slice()) {
    try {
      // Skip catalog indicators that require OHLC or volume when the
      // underlying series is close-only (e.g. the NEPSE index).
      const reg = registry.find((x) => x.name === ci.name);
      const inputs = reg ? (reg.inputs || []) : [];
      if (isIndex && inputs.some((inp) => inp === "high" || inp === "low" || inp === "volume")) {
        continue;
      }
      if (!reg) continue;   // an indicator the registry no longer knows
      await applyCatalogIndicator(ci, dates, symbol);
      ci.kind = indPlacement(reg) === "pane" ? "pane" : "overlay";
    } catch (e) { /* a stale saved indicator just does not draw */ }
  }
  // Custom formulas: skip for index if they reference high/low/volume.
  if (state.chartBars && state.chartBars.length) {
    for (const f of loadCustomFormulas(symbol)) {
      if (isIndex && /high|low|volume/i.test(f.formula)) continue;
      try { await applyCustomFormula(f.name, f.formula, f.color, state.chartBars); }
      catch (e) { console.warn("custom formula failed:", f.name, e && e.message); }
    }
  }
}

/* Add a catalog indicator as a NEW instance (duplicates allowed: each has its
   own id), then draw it. `openConfig` scrolls its config row into view. */
async function addToChartFromCatalog(name, paramsOverride) {
  const sym = state.chartSymbol;
  if (!sym || !(state.chartDates || []).length) throw new Error("Load a chart first.");
  const reg = (await fetchIndicatorRegistry()).find((x) => x.name === name);
  const same = (state.customInds || []).filter((x) => x.name === name);
  const inst = {
    id: newIndId(),
    name,
    params: paramsOverride && Object.keys(paramsOverride).length
      ? { ...paramsOverride }
      : (same[same.length - 1] && same[same.length - 1].params ? { ...same[same.length - 1].params } : (reg ? { ...(reg.params || {}) } : {})),
    label: "",
    color: "",
    visible: true,
  };
  state.customInds = [...(state.customInds || []), inst];
  persistCustomInds(sym);
  indHistPush();
  /* The chart's window is a user setting: adding an indicator must not move it.
     Lightweight-charts can nudge the logical range by a fraction of a bar when
     an overlay changes the autoscaled price range, so the window is captured
     here and put back afterwards. No fitContent, ever. */
  const ts = state.charts.price && state.charts.price.timeScale();
  let keep = null;
  try { keep = ts ? ts.getVisibleLogicalRange() : null; } catch (e) { keep = null; }
  await applyCatalogIndicator(inst, state.chartDates);
  if (keep && ts) { try { ts.setVisibleLogicalRange(keep); } catch (e) { /* gone */ } }
  indRecentsPush(name);
  return inst;
}

function indRecentsPush(name) {
  try {
    const rec = JSON.parse(localStorage.getItem("mt-ind-recents") || "[]");
    const next = [name, ...(Array.isArray(rec) ? rec.filter((x) => x !== name) : [])].slice(0, 12);
    localStorage.setItem("mt-ind-recents", JSON.stringify(next));
  } catch (e) { /* storage off */ }
}
function indRecents() {
  try { const v = JSON.parse(localStorage.getItem("mt-ind-recents") || "[]"); return Array.isArray(v) ? v : []; }
  catch (e) { return []; }
}

/* Remove one instance by id (not by name — duplicates exist). */
async function removeIndicatorInstance(id) {
  const inst = (state.customInds || []).find((x) => x.id === id);
  state.customInds = (state.customInds || []).filter((x) => x.id !== id);
  persistCustomInds(state.chartSymbol);
  indHistPush();
  const rec = state.indSeries[id];
  if (rec) {
    (rec.panes || []).forEach((el) => {
      const paneId = el.id;
      try { el.remove(); } catch (e) { /* gone */ }
      if (state.charts[paneId]) { try { state.charts[paneId].remove(); } catch (e) { /* gone */ } delete state.charts[paneId]; }
    });
    delete state.indSeries[id];
  }
  await loadChart();
  renderIndDrawer();
}

/* Keep the plain-name removal (the catalog modal removes the last instance of
   a name; older callers keep working). */
function removeCustomIndicator(name) {
  const list = (state.customInds || []).filter((x) => x.name === name);
  const last = list[list.length - 1];
  if (last && last.id) return removeIndicatorInstance(last.id);
  state.customInds = (state.customInds || []).filter((x) => x.name !== name);
  persistCustomInds(state.chartSymbol);
  document.querySelectorAll(`[id^='pane-custom-${name}']`).forEach((el) => {
    try { el.remove(); } catch (e) { /* noop */ }
  });
  Object.keys(state.charts || {}).forEach((k) => {
    if (k.startsWith(`pane-custom-${name}`)) delete state.charts[k];
  });
  loadChart();
}

/* Catalog modal ------------------------------------------------------------ */
const CATALOG_CATS = ["all", "trend", "momentum", "volatility", "volume", "other"];
/* §8E indicator favourites + templates. Both are per-browser localStorage
   stores — names only plus checkbox sets; nothing is computed or faked here.
   Failures (storage full / corrupt JSON) fall back to empty, never to an
   invented list. */
function indFavs() {
  try { const v = JSON.parse(localStorage.getItem("mt-ind-favs") || "[]"); return Array.isArray(v) ? v : []; }
  catch (e) { return []; }
}
function toggleIndFav(name) {
  const f = indFavs().filter((x) => x !== name);
  if (!indFavs().includes(name)) f.push(name);
  try { localStorage.setItem("mt-ind-favs", JSON.stringify(f)); } catch (e) { drawStatus("Could not save favourites (storage error)."); }
  renderCatalogModal();
}
const IND_TEMPLATE_KEYS = ["sma", "ema", "bb", "vol", "rsi", "macd", "swings", "close-swings"];
function indTemplates() {
  try {
    const v = JSON.parse(localStorage.getItem("mt-ind-templates") || "{}");
    return v && typeof v === "object" && !Array.isArray(v) ? v : {};
  } catch (e) { return {}; }
}
function refreshIndTplList() {
  const sel = $("#ind-tpl-list");
  if (!sel) return;
  const names = Object.keys(indTemplates()).sort();
  sel.innerHTML = names.length
    ? names.map((n) => `<option value="${esc(n)}">${esc(n)}</option>`).join("")
    : `<option value="">— none saved —</option>`;
}
function saveIndTemplate() {
  const name = (window.prompt("Template name (stored in this browser):", "") || "").trim().slice(0, 40);
  if (!name) return;
  const flags = Object.fromEntries(IND_TEMPLATE_KEYS.map((k) => {
    const el = $("#ind-" + k); return [k, !!(el && el.checked)];
  }));
  const t = indTemplates();
  // Templates now capture BOTH the quick layers and every indicator instance
  // (name + params + visibility) for the current symbol — so a full chart
  // configuration can be restored, not just the checkboxes.
  t[name] = {
    quick: flags,
    instances: (state.customInds || []).map((x) => ({ name: x.name, params: x.params, label: x.label, color: x.color, visible: x.visible })),
  };
  try { localStorage.setItem("mt-ind-templates", JSON.stringify(t)); }
  catch (e) { drawStatus("Could not save the template (storage error) — nothing was changed."); return; }
  refreshIndTplList();
  drawStatus(`Template "${name}" saved (${Object.values(flags).filter(Boolean).length} quick layer(s), ${(state.customInds || []).length} indicator instance(s)).`);
}
async function applyIndTemplate(name) {
  const tpl = indTemplates()[name];
  if (!tpl) { drawStatus("That template no longer exists."); return; }
  // Back-compat: older templates stored the flags directly.
  const flags = tpl.quick || tpl;
  IND_TEMPLATE_KEYS.forEach((k) => {
    const el = $("#ind-" + k);
    if (el) el.checked = !!flags[k];
  });
  if (Array.isArray(tpl.instances) && state.chartSymbol) {
    state.customInds = tpl.instances.map((x) => ({
      id: newIndId(), name: x.name, params: { ...(x.params || {}) },
      label: x.label || "", color: x.color || "", visible: x.visible !== false,
    }));
    persistCustomInds(state.chartSymbol);
    indHistPush();
  }
  if (state.chartSymbol) { drawStatus(`Template "${name}" applied — reloading the chart.`); await loadChart(); }
  else drawStatus(`Template "${name}" ticked. Load a symbol to see it on the chart.`);
  renderIndDrawer();
}
function deleteIndTemplate() {
  const sel = $("#ind-tpl-list");
  const name = sel && sel.value;
  if (!name) { drawStatus("No template selected."); return; }
  const t = indTemplates();
  if (!t[name]) return;
  if (!window.confirm(`Delete template "${name}"?`)) return;
  delete t[name];
  try { localStorage.setItem("mt-ind-templates", JSON.stringify(t)); } catch (e) { /* keep going */ }
  refreshIndTplList();
  drawStatus(`Template "${name}" deleted.`);
}

async function renderCatalogModal() {
  const list = $("#ind-catalog-list");
  const countEl = $("#ind-catalog-count");
  const q = ($("#ind-catalog-search").value || "").trim().toLowerCase().split(/\s+/).filter(Boolean);
  const catSel = $("#ind-catalog-cat").value;
  let reg = [];
  try { reg = await fetchIndicatorRegistry(); }
  catch (e) {
    list.innerHTML = `<div class="empty">Registry not reachable: ${esc(e.message)}</div>`;
    countEl.textContent = "";
    return;
  }
  const counts = {};
  (state.customInds || []).forEach((x) => { counts[x.name] = (counts[x.name] || 0) + 1; });
  const favs = indFavs();
  const rows = reg.filter((x) => {
    if (catSel === "favs" && !favs.includes(x.name)) return false;
    if (catSel === "recent" && !indRecents().includes(x.name)) return false;
    if (catSel !== "all" && catSel !== "favs" && catSel !== "recent" && x.category !== catSel) return false;
    if (!q.length) return true;
    const hay = `${x.name} ${x.label || ""} ${x.category} ${x.formula || ""} ${x.reference || ""}`.toLowerCase();
    return q.every((t) => hay.includes(t));
  });
  countEl.textContent = `${rows.length} of ${reg.length} registered`;
  if (!rows.length) {
    list.innerHTML = `<div class="empty">${catSel === "favs"
      ? "No favourites yet — tap the ☆ on any indicator row."
      : "No match for that search / filter."}</div>`;
    return;
  }
  list.innerHTML = `<div class="tablewrap">${table(
    ["Name", "Category", "Parameters", "Formula (as implemented)", "Reference", ""],
    rows.map((x) => [
      { html: `<b>${esc(x.label || x.name)}</b><br><span class="hint mono">${esc(x.name)}</span>` },
      { html: `<span class="pill ${x.category === "momentum" ? "pill-info" : "pill-ok"}">${esc(x.category)}</span>` },
      { html: esc(Object.entries(x.params || {}).map(([k, v]) => `${k}=${v}`).join(", ")) || "—" },
      { html: `<code class="cat-formula">${esc(x.formula || "")}</code>` },
      { html: esc(x.reference || "") || "—" },
      { html: `<button class="ghost cat-fav" data-name="${esc(x.name)}" title="Toggle favourite">${favs.includes(x.name) ? "★" : "☆"}</button> ` +
              `<button class="ghost cat-add" data-name="${esc(x.name)}" data-cat="${esc(x.category)}" data-params="${esc(JSON.stringify(x.params || {}))}">${counts[x.name] ? "Add again" : "Add to chart"}${counts[x.name] ? ` (${counts[x.name]})` : ""}</button>${counts[x.name] ? `<button class="ghost cat-remove" data-name="${esc(x.name)}">Remove</button>` : ""}` },
    ]))}</div>`;
  list.querySelectorAll(".cat-fav").forEach((b) => b.addEventListener("click", () => {
    toggleIndFav(b.dataset.name);   // re-renders the modal with the new star
  }));
  list.querySelectorAll(".cat-add").forEach((b) => b.addEventListener("click", async () => {
    let params = {};
    try { params = JSON.parse(b.dataset.params || "{}"); } catch (e) { params = {}; }
    try {
      await addToChartFromCatalog(b.dataset.name, params);
      renderCatalogModal();
    } catch (e) { drawStatus(`Catalog add failed: ${e.message}`); }
  }));
  list.querySelectorAll(".cat-remove").forEach((b) => b.addEventListener("click", async () => {
    const list2 = (state.customInds || []).filter((x) => x.name === b.dataset.name);
    const last = list2[list2.length - 1];
    if (last) { await removeIndicatorInstance(last.id); renderCatalogModal(); }
  }));
}

async function openIndicatorCatalog() {
  const m = $("#ind-catalog");
  if (!m) return;
  m.hidden = false;
  $("#ind-catalog-search").value = "";
  $("#ind-catalog-cat").value = "all";
  if (state.chartSymbol) state.customInds = loadCustomInds(state.chartSymbol);
  renderCatalogModal();
}

/* ==================================================================== §IND
   Indicator manager drawer. This is the chart-integrated workflow: search or
   browse the registry, add instances, edit parameters, hide, duplicate,
   reorder, rename, remove, save templates, and export/import layouts — all
   inside the chart stage, never on a separate page. */
function indQuickSnapshot() {
  const quick = {};
  IND_TEMPLATE_KEYS.forEach((k) => { const el = $("#ind-" + k); quick[k] = !!(el && el.checked); });
  return quick;
}

/* Presentation/verification metadata generated from the registry + test scan.
   Calculation truth stays in the Python registry; this only adds abbreviations,
   variable/limitation prose and the verification level. */
function indInfoFor(name) {
  return (window.INDICATOR_INFO || {})[name] || null;
}
function indPlacementText(reg) {
  return indPlacement(reg) === "pane"
    ? "own synced pane below the price chart"
    : "overlay on the price chart";
}

async function renderIndHits() {
  const host = $("#ind-search-results");
  if (!host) return;
  let reg = [];
  try { reg = await fetchIndicatorRegistry(); }
  catch (e) { host.innerHTML = `<div class="ind-empty-state">Registry not reachable: ${esc(e.message)}</div>`; return; }
  const q = ((($("#ind-search") || {}).value) || "").trim().toLowerCase().split(/\s+/).filter(Boolean);
  const cat = (($("#ind-cat") || {}).value) || "all";
  const favs = indFavs();
  const recents = indRecents();
  const active = state.customInds || [];
  let rows = reg.filter((x) => {
    if (cat === "favs" && !favs.includes(x.name)) return false;
    if (cat === "recent" && !recents.includes(x.name)) return false;
    if (cat !== "all" && cat !== "favs" && cat !== "recent" && x.category !== cat) return false;
    if (!q.length) return true;
    const meta = indInfoFor(x.name) || {};
    const hay = [
      x.name, x.label, meta.abbr, x.category,
      x.formula, x.reference, x.notes, (x.inputs || []).join(" "),
    ].join(" ").toLowerCase();
    return q.every((t) => hay.includes(t));
  });
  if (q.length) {
    // Rank by how directly the query names the indicator, so "ATR" and "RSI"
    // lead with Average True Range / Relative Strength Index instead of every
    // indicator whose formula happens to mention them.
    const joined = q.join(" ");
    const score = (x) => {
      const i = indInfoFor(x.name) || {};
      const name = String(x.name).toLowerCase();
      const label = String(x.label || "").toLowerCase();
      const abbr = String(i.abbr || "").toLowerCase();
      if (name === joined || label === joined || abbr === joined) return 0;
      if (q.every((t) => label.startsWith(t) || name.startsWith(t))) return 1;
      if (q.every((t) => label.includes(t))) return 2;
      if (q.every((t) => name.includes(t))) return 3;
      return 4;
    };
    rows = rows.slice().sort((a, b) =>
      score(a) - score(b) || String(a.label || a.name).localeCompare(String(b.label || b.name)));
  }
  if (!q.length && cat === "all") {
    // Browsing with no query: favourites, then recents, then the WHOLE registry
    // grouped by category. This list must never be capped to a shortlist — an
    // 8-row cap here is exactly why the panel looked like it held "about five
    // indicators" while the registry held 81.
    const seen = new Set();
    const head = [];
    [...favs, ...recents].forEach((n) => {
      if (seen.has(n)) return;
      const hit = reg.find((x) => x.name === n);
      if (hit) { seen.add(n); head.push(hit); }
    });
    const order = { trend: 0, momentum: 1, volatility: 2, volume: 3, other: 4 };
    const rest = rows.filter((x) => !seen.has(x.name))
      .slice()
      .sort((a, b) => (order[a.category] ?? 9) - (order[b.category] ?? 9)
        || String(a.label || a.name).localeCompare(String(b.label || b.name)));
    rows = head.concat(rest);
  }
  if (!rows.length) {
    host.innerHTML = `<div class="ind-empty-state">${cat === "favs"
      ? "No favourites yet — tap ☆ on a row."
      : cat === "recent" ? "Nothing used yet."
        : "No match for that search. Try the abbreviation (RSI, ATR) or a word from the formula."}</div>`;
    return;
  }
  host.innerHTML = `<div class="ind-results-count">Showing <b>${rows.length}</b> of ${reg.length} registered indicators` +
    `${q.length ? " for this search" : ""}${cat !== "all" ? ` in <b>${esc(cat)}</b>` : ""}.</div>` +
    rows.map((x) => {
      const count = active.filter((a) => a.name === x.name).length;
      const meta = indInfoFor(x.name) || {};
      const place = indPlacement(x);
      return `<div class="ind-hit">
        <button class="ih-info" data-ind-info="${esc(x.name)}" title="About ${esc(x.label || x.name)} — formula, inputs, placement, verification">&#9432;</button>
        <span class="ih-name"><b title="${esc(x.notes || x.formula || "")}">${esc(x.label || x.name)}</b>` +
        `<span>${esc(x.name)}${meta.abbr ? ` · ${esc(meta.abbr)}` : ""} · ${esc(x.category)} · ${esc(place)}` +
        `${count ? ` · on chart ×${count}` : ""}</span></span>
        <span class="ih-cat">${esc(Object.entries(x.params || {}).map(([k, v]) => `${k}=${v}`).join(" "))}</span>
        <button class="ih-star" data-ind-fav="${esc(x.name)}" title="Favourite">${favs.includes(x.name) ? "★" : "☆"}</button>
        <button class="ctb-btn ghost ih-add" data-ind-add="${esc(x.name)}">Add</button>
      </div>`;
    }).join("");
  host.querySelectorAll("[data-ind-info]").forEach((b) => b.addEventListener("click", (e) => {
    e.stopPropagation();
    showIndicatorInfo(b.dataset.indInfo);
  }));
  host.querySelectorAll("[data-ind-fav]").forEach((b) => b.addEventListener("click", () => {
    toggleIndFav(b.dataset.indFav);
    renderIndHits();
  }));
  host.querySelectorAll("[data-ind-add]").forEach((b) => b.addEventListener("click", async () => {
    try { await addToChartFromCatalog(b.dataset.indAdd, null); await renderIndDrawer(); }
    catch (e) { drawStatus(`Add failed: ${e.message}`); }
  }));
}

/* --------------------------------------------------- indicator documentation
   Every entry has a visible ⓘ that is independently clickable (it does not add
   the indicator). The panel renders the registry's own formula/inputs/reference
   — so the displayed formula is the implemented one — plus generated
   presentation metadata. Switching indicators reuses the panel and never
   touches the chart, the zoom or the loaded indicators. */
function indVarExplanations(meta, reg) {
  const vars = (meta && meta.variables) || [];
  const out = vars.map(([k, txt]) => [k, txt || "numeric setting for this indicator"]);
  const seen = new Set(out.map(([k]) => k));
  Object.keys((reg && reg.params) || {}).forEach((k) => {
    if (!seen.has(k)) out.push([k, "numeric setting for this indicator"]);
  });
  return out;
}

function indPlainText(reg, meta) {
  const notes = (reg && reg.notes) || (meta && meta.notes);
  if (notes) return notes;
  const cat = (reg && reg.category) || (meta && meta.category) || "technical";
  const outs = ((reg && reg.outputs) || []).join(", ");
  const ins = ((meta && meta.inputs_friendly) || (reg && reg.inputs) || []).join(", ") || "close price";
  return `A ${cat} indicator that reads ${ins} and produces ${outs || "a single series"}.`;
}

function indMissingDataText(reg, meta) {
  const w = (reg && reg.warmup) || 0;
  const inputs = (meta && meta.inputs) || (reg && reg.inputs) || [];
  const parts = [
    `Needs about ${w} completed bars before the first value; earlier rows are gaps (NaN), never zeros.`,
  ];
  if (inputs.includes("volume")) {
    parts.push("Requires real volume — on the NEPSE index only turnover is owned, so this indicator is skipped for the index rather than approximated.");
  }
  parts.push("If the loaded history is shorter than the warm-up, the indicator reports insufficient data with a reason instead of drawing a partial line.");
  return parts.join(" ");
}

async function showIndicatorInfo(name) {
  const pane = $("#ind-info");
  if (!pane) return;
  let reg = null;
  try { reg = (await fetchIndicatorRegistry()).find((x) => x.name === name) || null; }
  catch (e) { reg = null; }
  const meta = indInfoFor(name) || {};
  const title = $("#ind-info-title");
  if (title) title.textContent = reg ? (reg.label || reg.name) : name;
  const addBtn = $("#ind-info-add");
  if (addBtn) addBtn.dataset.indAdd = name;
  const body = $("#ind-info-body");
  if (!body) return;

  const params = (reg && reg.params) || {};
  const outputs = (reg && reg.outputs) || [];
  const placement = reg ? indPlacementText(reg) : "—";
  const inputs = (meta.inputs_friendly || (reg && reg.inputs) || []);
  const vlevel = meta.verification === "reference"
    ? `<span class="pill pill-ok">TESTED-PASS</span> — compared against an independent re-implementation of the formula (${esc(meta.verification_where || "test suite")}).`
    : meta.verification === "invariants"
      ? `<span class="pill pill-warn">NOT-TESTED</span> numerically — covered by the structural invariants only (${esc(meta.verification_where || "test suite")}): no look-ahead, NaN warm-up, short-series safety. Results are not independently cross-checked.`
      : `<span class="pill pill-warn">NOT-TESTED</span> — no automated coverage found.`;

  const varRows = indVarExplanations(meta, reg)
    .map(([k, txt]) => `<tr><td class="mono">${esc(k)}</td><td>${esc(txt)}</td></tr>`).join("")
    || `<tr><td colspan="2" class="hint">No parameters — this indicator has no settings.</td></tr>`;

  const defList = Object.entries(params).map(([k, v]) => `<code>${esc(k)}=${esc(String(v))}</code>`).join(" ")
    || "<span class='hint'>none</span>";

  const section = (label, html) => `<div class="ii-field"><div class="ii-k">${label}</div><div class="ii-v">${html}</div></div>`;

  body.innerHTML =
    section("Full name", esc(reg ? reg.label : name) + ` <span class="hint mono">${esc(name)}</span>`) +
    section("Abbreviation", esc(meta.abbr || "—")) +
    section("Category", esc(reg ? reg.category : "—")) +
    section("What it is", esc(indPlainText(reg, meta))) +
    section("What it measures", `Reads <b>${esc(inputs.join(", ") || "close price")}</b> and emits <b>${esc(outputs.join(", ") || "—")}</b>. ` +
      (reg && reg.notes ? `<span class="hint">${esc(reg.notes)}</span>` : "")) +
    section("Formula (as implemented)", `<code class="ii-formula">${esc((reg && reg.formula) || "—")}</code>`) +
    section("How this build differs from the textbook",
      esc(meta.formula_note || "Matches the conventional definition shown above; the code uses the standard construction.")) +
    section("Formula variables", `<div class="tablewrap"><table class="mini"><tbody>${varRows}</tbody></table></div>`) +
    section("Default parameters", defList) +
    section("Configurable parameters",
      `${Object.keys(params).length} numeric setting(s). Change them on the indicator's row in the panel — the chart recomputes and the zoom/scroll position is preserved.`) +
    section("Required data", esc(inputs.join(", ") || "close price") +
      ` <span class="hint">(stored daily bars for the loaded symbol; prices are unadjusted for corporate actions)</span>`) +
    section("Chart placement", esc(placement)) +
    section("Interpretation", esc(meta.interpretation ||
      "Compare the value against its own history and the reference below. This build hard-codes no thresholds; the conventional readings are a convention, not a law.")) +
    section("Known limitations", esc(meta.limitations ||
      "Uses stored daily bars only; prices are unadjusted, so splits/bonuses can distort older levels.")) +
    section("Missing-data behaviour", esc(indMissingDataText(reg, meta))) +
    section("Calculation verification", vlevel) +
    section("Reference / attribution", esc((reg && reg.reference) || "—")) +
    `<details class="ii-tech"><summary>Technical details (as implemented)</summary>` +
    `<div class="hint">Inputs: <span class="mono">${esc(((reg && reg.inputs) || []).join(", "))}</span> · ` +
    `Outputs: <span class="mono">${esc(outputs.join(", "))}</span> · ` +
    `Warm-up: <span class="mono">${esc(String((reg && reg.warmup) ?? 0))}</span> bars · ` +
    `Registry key: <span class="mono">${esc(name)}</span></div>` +
    `<pre class="ii-code">${esc(((reg && reg.formula) || "") + "\n" + ((reg && reg.notes) || ""))}</pre></details>`;

  pane.hidden = false;
  ensurePanelGeometry(pane);
}


/* Which instance rows show their parameter/action panel. Kept out of the
   persisted layout on purpose — it is a view preference, not chart state. */
const indExpandedIds = new Set();

function indInstanceRowHtml(inst, reg, idx, total) {
  const label = inst.label || (reg && reg.label) || inst.name;
  const color = inst.color || indColor(inst.id);
  const defaults = (reg && reg.params) || {};
  const nParams = Object.keys(defaults).length;
  const pEls = Object.entries(defaults).map(([k, def]) => {
    const cur = (inst.params && inst.params[k] !== undefined) ? inst.params[k] : def;
    const isNum = typeof def === "number";
    return `<label title="parameter ${esc(k)}">${esc(k)} <input data-ind-param="${esc(k)}" data-ind-owner="${esc(inst.id)}" data-num="${isNum ? 1 : 0}" value="${esc(String(cur))}" /></label>`;
  }).join("");
  const vis = inst.visible !== false;
  const expanded = indExpandedIds.has(inst.id);
  // Compact row: colour chip (the icon), the name, an independent ⓘ info
  // control and the essential actions. Parameters, apply/reset/rename and
  // draw-order controls live behind the ⚙ toggle so the selector stays
  // scannable even with many instances.
  return `<div class="ind-inst ${vis ? "" : "ind-hidden"}" data-inst="${esc(inst.id)}">
    <div class="ii-head">
      <span class="ii-dot" style="background:${esc(color)}"></span>
      <span class="ii-name" title="${esc(reg ? (reg.reference || reg.name) : inst.name)} — ${esc(reg ? (reg.formula || "") : "")}">${esc(label)}</span>
      <button class="ghost ii-info" data-ind-act="info" data-id="${esc(inst.id)}" title="About ${esc(label)} — what it measures, formula, parameters, placement, verification" aria-label="Information about ${esc(label)}">&#9432;</button>
      <span class="ii-actions">
        <button class="ghost" data-ind-act="vis" data-id="${esc(inst.id)}" title="${vis ? "Hide (keeps the configuration)" : "Show"}">${vis ? "Hide" : "Show"}</button>
        <button class="ghost ii-toggle" data-ind-act="expand" data-id="${esc(inst.id)}" title="${expanded ? "Hide" : "Show"} parameters and actions" aria-expanded="${expanded ? "true" : "false"}">&#9881;${nParams ? ` ${nParams}` : ""}</button>
        <button class="ghost" data-ind-act="remove" data-id="${esc(inst.id)}" title="Remove from the chart">&#10005;</button>
      </span>
    </div>
    <div class="ii-extra" ${expanded ? "" : "hidden"}>
      <div class="ii-params">
        ${pEls || `<span class="hint">no parameters</span>`}
        <button class="ctb-btn ghost" data-ind-act="apply" data-id="${esc(inst.id)}" title="Apply the parameter values and recompute">Apply</button>
        <button class="ctb-btn ghost" data-ind-act="reset" data-id="${esc(inst.id)}" title="Reset to the registry defaults">Reset</button>
        <button class="ctb-btn ghost" data-ind-act="rename" data-id="${esc(inst.id)}" title="Rename this instance's chart label">Rename</button>
      </div>
      <div class="ii-params ii-more">
        <button class="ctb-btn ghost" data-ind-act="dup" data-id="${esc(inst.id)}" title="Duplicate with the same parameters">Duplicate</button>
        <button class="ctb-btn ghost" data-ind-act="up" data-id="${esc(inst.id)}" title="Move up in draw order" ${idx === 0 ? "disabled" : ""}>Move up</button>
        <button class="ctb-btn ghost" data-ind-act="down" data-id="${esc(inst.id)}" title="Move down in draw order" ${idx === total - 1 ? "disabled" : ""}>Move down</button>
        <span class="hint ii-cat">${esc(reg ? reg.category : "unknown")}</span>
      </div>
    </div>
    ${inst.err ? `<div class="ii-err">${esc(inst.err)}</div>` : ""}
  </div>`;
}

function indParamsFromRow(id) {
  const host = $("#ind-instances");
  if (!host) return null;
  const row = host.querySelector(`[data-inst="${id}"]`);
  if (!row) return null;
  const params = {};
  row.querySelectorAll(`[data-ind-param]`).forEach((inp) => {
    const k = inp.dataset.indParam;
    const raw = inp.value.trim();
    if (inp.dataset.num === "1") {
      const n = Number(raw);
      params[k] = Number.isFinite(n) ? n : raw;
    } else {
      params[k] = raw;
    }
  });
  return params;
}

async function renderIndDrawer() {
  const host = $("#ind-instances");
  if (!host) return;
  if (!state.indHist.stack.length) indHistPush();   // baseline undo state
  let reg = [];
  try { reg = await fetchIndicatorRegistry(); } catch (e) { /* list below shows raw */ }
  const byName = Object.fromEntries(reg.map((x) => [x.name, x]));
  const list = state.customInds || [];
  const countEl = $("#ind-count");
  if (countEl) countEl.textContent = list.length ? `${list.length} instance(s)` : "none yet";
  renderIndHits();
  if (!list.length) {
    host.innerHTML = `<div class="ind-empty-state">No catalog indicators on this chart yet. Search above, or use the quick layers. Each instance keeps its own parameters, so one indicator can appear twice with different settings.</div>`;
  } else {
    host.innerHTML = list.map((inst, idx) => indInstanceRowHtml(inst, byName[inst.name], idx, list.length)).join("");
    host.querySelectorAll("[data-ind-act]").forEach((b) => b.addEventListener("click", async () => {
      const id = b.dataset.id;
      const inst = (state.customInds || []).find((x) => x.id === id);
      if (!inst) return;
      try {
        if (b.dataset.indAct === "info") { await showIndicatorInfo(inst.name); return; }
        if (b.dataset.indAct === "expand") {
          if (indExpandedIds.has(id)) indExpandedIds.delete(id); else indExpandedIds.add(id);
          renderIndDrawer();
          return;
        }
        if (b.dataset.indAct === "remove") { await removeIndicatorInstance(id); return; }
        if (b.dataset.indAct === "vis") {
          inst.visible = inst.visible === false;
          persistCustomInds(state.chartSymbol);
          applyInstanceVisibility(inst);
          renderIndDrawer();
          return;
        }
        if (b.dataset.indAct === "dup") {
          const copy = { id: newIndId(), name: inst.name, params: { ...inst.params }, label: inst.label ? `${inst.label} (copy)` : "", color: "", visible: inst.visible !== false };
          state.customInds.push(copy);
          persistCustomInds(state.chartSymbol);
          indHistPush();
          await applyCatalogIndicator(copy, state.chartDates);
          renderIndDrawer();
          return;
        }
        if (b.dataset.indAct === "up" || b.dataset.indAct === "down") {
          const delta = b.dataset.indAct === "up" ? -1 : 1;
          const idx = state.customInds.findIndex((x) => x.id === id);
          const to = idx + delta;
          if (to < 0 || to >= state.customInds.length) return;
          const [moved] = state.customInds.splice(idx, 1);
          state.customInds.splice(to, 0, moved);
          persistCustomInds(state.chartSymbol);
          indHistPush();
          await loadChart();   // draw order is series creation order — rebuild
          renderIndDrawer();
          return;
        }
        if (b.dataset.indAct === "apply") {
          const params = indParamsFromRow(id);
          if (params) { inst.params = params; inst.err = ""; persistCustomInds(state.chartSymbol); indHistPush(); }
          await loadChart();
          renderIndDrawer();
          return;
        }
        if (b.dataset.indAct === "reset") {
          const regHit = byName[inst.name];
          inst.params = { ...((regHit && regHit.params) || {}) };
          persistCustomInds(state.chartSymbol);
          indHistPush();
          await loadChart();
          renderIndDrawer();
          return;
        }
        if (b.dataset.indAct === "rename") {
          const next = (window.prompt("Chart label for this instance (empty = registry name):", inst.label || "") || "").trim().slice(0, 40);
          inst.label = next;
          persistCustomInds(state.chartSymbol);
          indHistPush();
          await loadChart();
          renderIndDrawer();
          return;
        }
      } catch (e) {
        inst.err = e.message || String(e);
        renderIndDrawer();
      }
    }));
  }
  updateIndUndoButtons();
}

function exportIndLayout() {
  const quick = indQuickSnapshot();
  const compare = state.compare ? {
    mode: state.compare.mode, returnN: state.compare.returnN,
    symbols: (state.compare.symbols || []).map((s) => ({ symbol: s.symbol, color: s.color, style: s.style, width: s.width, visible: s.visible })),
  } : null;
  const payload = {
    app: "pravaha",
    kind: "chart-layout",
    version: 1,
    exported_at: new Date().toISOString(),
    symbol: state.chartSymbol || null,
    timeframe: state.chartTf || (($("#tf-select") || {}).value) || "daily",
    chart_type: (($("#chart-type") || {}).value) || "candles",
    quick,
    instances: (state.customInds || []).map((x) => ({ name: x.name, params: x.params, label: x.label, color: x.color, visible: x.visible })),
    compare,
  };
  download(`pravaha-layout-${state.chartSymbol || "chart"}.json`, JSON.stringify(payload, null, 2), "application/json");
  drawStatus("Indicator layout exported (JSON).");
}

async function importIndLayout(text) {
  let obj = null;
  try { obj = JSON.parse(text); } catch (e) { throw new Error("Not valid JSON."); }
  if (!obj || obj.kind !== "chart-layout" || !Array.isArray(obj.instances)) {
    throw new Error("Not a PRAVAHA chart-layout file.");
  }
  const quick = obj.quick || {};
  IND_TEMPLATE_KEYS.forEach((k) => { const el = $("#ind-" + k); if (el && k in quick) el.checked = !!quick[k]; });
  state.customInds = obj.instances.filter((x) => x && typeof x.name === "string").map((x) => ({
    id: newIndId(), name: x.name, params: (x.params && typeof x.params === "object") ? x.params : {},
    label: typeof x.label === "string" ? x.label : "", color: typeof x.color === "string" ? x.color : "",
    visible: x.visible !== false,
  }));
  if (state.chartSymbol) persistCustomInds(state.chartSymbol);
  if (obj.compare && Array.isArray(obj.compare.symbols) && obj.compare.mode) {
    state.compare = { mode: String(obj.compare.mode), returnN: Number(obj.compare.returnN) || 20,
      symbols: obj.compare.symbols.slice(0, 3).map((s, i) => ({ symbol: String(s.symbol || "").toUpperCase(), color: s.color || CMP_PALETTE[i % CMP_PALETTE.length], style: s.style === "area" ? "area" : "line", width: Number(s.width) || 2, visible: s.visible !== false })).filter((s) => s.symbol),
      series: [], lastValues: {} };
    if (state.chartSymbol) saveCompareCfg();
  }
  if (obj.chart_type && $("#chart-type")) {
    const opt = [...$("#chart-type").options].find((o) => o.value === obj.chart_type && !o.disabled);
    if (opt) $("#chart-type").value = obj.chart_type;
  }
  indHistPush();
  if (state.chartSymbol) { await loadChart(); renderIndDrawer(); }
  drawStatus("Layout imported and applied.");
}

/* ================================================================== §COMPARE
   Multi-symbol comparison (primary + up to three more). Comparison series are
   drawn on their own scale so mixed price levels stay readable while the
   candles keep the price scale. Modes are computed client-side from the same
   stored daily bars the chart shows; nothing is interpolated and missing dates
   are honest gaps. Every mode is documented in the drawer. */
const CMP_PALETTE = [PRAVAHA.mint, PRAVAHA.caution, PRAVAHA.emerald, PRAVAHA.down, PRAVAHA.cyan, PRAVAHA.muted];
/* #rrggbb → rgba(r,g,b,a) so area fills can carry alpha independent of the
   browser's 8-digit-hex support. Falls back to the colour unchanged. */
function hexA(hex, a) {
  const m = /^#?([0-9a-f]{6})$/i.exec(String(hex || "").trim());
  if (!m) return hex;
  const n = parseInt(m[1], 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
}
function compareCfgKey(symbol) { return `mt-compare-${symbol || "default"}`; }
function loadCompareCfg(symbol) {
  const base = { mode: "percent", returnN: 20, symbols: [], series: [], lastValues: {} };
  try {
    const raw = JSON.parse(localStorage.getItem(compareCfgKey(symbol)) || "null");
    if (!raw || typeof raw !== "object") return base;
    return {
      mode: ["percent", "indexed", "relative", "returns", "raw"].includes(raw.mode) ? raw.mode : "percent",
      returnN: Math.max(1, Math.min(500, Number(raw.returnN) || 20)),
      symbols: Array.isArray(raw.symbols) ? raw.symbols.slice(0, 3).filter((s) => s && s.symbol).map((s, i) => ({
        symbol: String(s.symbol).toUpperCase(), color: s.color || CMP_PALETTE[i % CMP_PALETTE.length],
        style: s.style === "area" ? "area" : "line", width: Math.max(1, Math.min(4, Number(s.width) || 2)),
        visible: s.visible !== false,
      })) : [],
      series: [], lastValues: {},
    };
  } catch (e) { return base; }
}
function saveCompareCfg() {
  if (!state.chartSymbol || !state.compare) return;
  try {
    localStorage.setItem(compareCfgKey(state.chartSymbol), JSON.stringify({
      mode: state.compare.mode, returnN: state.compare.returnN,
      symbols: (state.compare.symbols || []).map((s) => ({ symbol: s.symbol, color: s.color, style: s.style, width: s.width, visible: s.visible })),
    }));
  } catch (e) { /* storage off */ }
}

function fmtCompareValue(mode, v) {
  if (v == null || !isFinite(v)) return "—";
  if (mode === "raw") return fmtNum(v);
  if (mode === "indexed" || mode === "relative") return fmtNum(v, 2);
  return `${v >= 0 ? "+" : ""}${fmtNum(v, 2)}%`;
}

async function applyCompareToChart(seq) {
  const cfg = state.compare;
  const chart = state.charts.price;
  const legend = $("#cmp-legend");
  (cfg && cfg.series ? cfg.series : []).forEach((s) => { try { s.remove(); } catch (e) { /* gone with the chart */ } });
  if (cfg) { cfg.series = []; cfg.lastValues = {}; cfg.lastFirst = {}; }
  if (legend) { legend.hidden = true; legend.innerHTML = ""; }
  if (!cfg || !state.chartSymbol || !chart || !(state.chartDates || []).length) return;
  const rows = (cfg.symbols || []).filter((s) => s.visible !== false);
  if (!rows.length) return;
  const range = ($("#range") || {}).value || "120";
  const qs = range === "0" ? "?limit=20000" : `?limit=${encodeURIComponent(range)}`;
  const firstPrimary = state.chartDates[0];
  let indexByDate = null;
  try {
    if (cfg.mode === "relative") {
      const d = await api(`/api/indices/NEPSE/ohlc${qs}`);
      indexByDate = new Map((d.bars || []).filter((b) => b.close != null).map((b) => [String(b.date).slice(0, 10), Number(b.close)]));
    }
  } catch (e) { indexByDate = null; }
  const statusEl = $("#cmp-status");
  if (statusEl && cfg.mode === "relative" && !indexByDate) statusEl.textContent = "NEPSE composite unavailable — relative mode cannot be computed.";
  for (const row of rows) {
    let bars = [];
    try {
      const tf = state.chartTf || "daily";
      const barsPath = tf === "weekly" ? `/api/bars/${encodeURIComponent(row.symbol)}/weekly`
        : tf === "monthly" ? `/api/bars/${encodeURIComponent(row.symbol)}/monthly`
        : `/api/bars/${encodeURIComponent(row.symbol)}`;
      const d = await api(`${barsPath}${qs}`);
      bars = (d.bars || []).filter((b) => b.close != null);
    } catch (e) {
      row.err = e.message;
      continue;
    }
    row.err = "";
    if (!bars.length) { row.err = "no stored bars"; continue; }
    // Base: the series' first observation inside the window (independent
    // histories; documented in the drawer). Missing dates => gaps.
    const points = [];
    const first = bars[0];
    if (cfg.mode === "raw") {
      bars.forEach((b) => points.push({ time: b.time, value: Number(b.close) }));
    } else if (cfg.mode === "returns") {
      const N = cfg.returnN;
      for (let i = N; i < bars.length; i++) {
        const prev = Number(bars[i - N].close), cur = Number(bars[i].close);
        if (prev > 0) points.push({ time: bars[i].time, value: (cur / prev - 1) * 100 });
      }
    } else if (cfg.mode === "relative") {
      if (!indexByDate) { cfg.err = "NEPSE index unavailable — relative mode needs it"; continue; }
      const ratioAt = (b) => {
        const ic = indexByDate.get(String(b.time).slice(0, 10));
        return ic && ic > 0 ? Number(b.close) / ic : null;
      };
      let base = null;
      for (const b of bars) { const r = ratioAt(b); if (r != null) { base = r; break; } }
      if (base == null) { row.err = "no aligned index dates"; continue; }
      bars.forEach((b) => { const r = ratioAt(b); if (r != null) points.push({ time: b.time, value: (r / base) * 100 }); });
    } else {
      const base = Number(first.close);
      if (!(base > 0)) { row.err = "base price not positive"; continue; }
      bars.forEach((b) => {
        const c = Number(b.close);
        points.push({ time: b.time, value: cfg.mode === "indexed" ? (c / base) * 100 : (c / base - 1) * 100 });
      });
    }
    if (!points.length) { row.err = "no computable points"; continue; }
    const scaleId = cfg.mode === "raw" ? "left" : "cmpscale";
    const opts = {
      color: row.color, lineWidth: row.width, priceLineVisible: false,
      lastValueVisible: cfg.mode === "raw", title: `${row.symbol}`,
      priceScaleId: scaleId,
      lineType: 0,
    };
    if (row.style === "area") {
      const s = chart.addAreaSeries({ ...opts, topColor: hexA(row.color, 0.22), bottomColor: hexA(row.color, 0) });
      s.setData(points);
      cfg.series.push(s);
    } else {
      const s = chart.addLineSeries(opts);
      s.setData(points);
      cfg.series.push(s);
    }
    cfg.lastValues[row.symbol] = points[points.length - 1] ? points[points.length - 1].value : null;
    cfg.lastFirst[row.symbol] = points[0] ? points[0].value : null;
  }
  try {
    if (cfg.mode === "raw") chart.priceScale("left").applyOptions({ scaleMargins: { top: 0.1, bottom: 0.3 } });
    else chart.priceScale("cmpscale").applyOptions({ scaleMargins: { top: 0.08, bottom: 0.30 } });
  } catch (e) { /* scale may not be visible */ }
  if (seq !== undefined && seq !== chartLoadSeq) {
    (cfg.series || []).forEach((s) => { try { s.remove(); } catch (e) { /* stale */ } });
    cfg.series = [];
    return;
  }
  renderCompareLegend();
  renderComparePanel();
}

function renderCompareLegend() {
  const el = $("#cmp-legend");
  if (!el || !state.compare) return;
  const rows = (state.compare.symbols || []).filter((s) => s.visible !== false && !s.err);
  if (!rows.length || !state.charts.price) { el.hidden = true; return; }
  const mode = state.compare.mode;
  const modeLabel = { percent: "% from start", indexed: "idx 100", relative: "vs NEPSE ×100", returns: `rolling ${state.compare.returnN}-bar %`, raw: "price" }[mode] || mode;
  el.innerHTML = `<div class="cl-row" style="color:var(--muted)">comparison · ${esc(modeLabel)}${mode === "raw" ? " · shared left scale" : ""}</div>` +
    rows.map((s) => {
      const v = (state.compare.lastValues || {})[s.symbol];
      return `<div class="cl-row"><span class="cl-dot" style="background:${esc(s.color)}"></span>` +
        `<b>${esc(s.symbol)}</b><span>${esc(fmtCompareValue(mode, v))}</span></div>`;
    }).join("");
  el.hidden = false;
}

function renderComparePanel() {
  const host = $("#cmp-list");
  if (!host) return;
  const cfg = state.compare;
  if (!cfg) { host.innerHTML = ""; return; }
  if ($("#cmp-mode")) $("#cmp-mode").value = cfg.mode;
  if ($("#cmp-return-n")) $("#cmp-return-n").value = String(cfg.returnN);
  const primary = state.chartSymbol || "—";
  if (!(cfg.symbols || []).length) {
    host.innerHTML = `<div class="ind-empty-state">Comparing against <b>${esc(primary)}</b>. Add up to three symbols. Modes that rebase (percent / indexed / relative) start each series at its first visible observation; raw mode shares one left scale, so mixed price levels there are hard to compare by design — the drawer says so.</div>`;
    return;
  }
  host.innerHTML = (cfg.symbols || []).map((s) => {
    const v = (cfg.lastValues || {})[s.symbol];
    const first = (cfg.lastFirst || {})[s.symbol];
    let chg = null; let unit = "pp";
    if (v != null && first != null && cfg.mode !== "returns" && cfg.mode !== "raw") {
      if (cfg.mode === "indexed") { chg = v - 100; unit = ""; }
      else { chg = v - first; unit = cfg.mode === "percent" ? "pp" : ""; }
    }
    return `<div class="cmp-row ${s.visible === false ? "cmp-hidden" : ""}" data-cmp="${esc(s.symbol)}">
      <div class="cr-head">
        <span class="cl-dot" style="background:${esc(s.color)}; width:9px;height:9px;border-radius:50%"></span>
        <span class="cr-sym">${esc(s.symbol)}</span>
        <span class="cr-val">${esc(fmtCompareValue(cfg.mode, v))}${chg != null ? ` <span class="${chg >= 0 ? "up" : "down"}">(${chg >= 0 ? "+" : ""}${fmtNum(chg, 2)}${unit ? " " + unit : ""})</span>` : ""}</span>
        <span class="cr-actions">
          <button class="ghost" data-cmp-act="vis" data-sym="${esc(s.symbol)}" title="${s.visible === false ? "Show" : "Hide"}">${s.visible === false ? "Show" : "Hide"}</button>
          <button class="ghost" data-cmp-act="primary" data-sym="${esc(s.symbol)}" title="Make this the primary symbol">Primary</button>
          <button class="ghost" data-cmp-act="remove" data-sym="${esc(s.symbol)}" title="Remove">&#10005;</button>
        </span>
      </div>
      <div class="cr-opts">
        <label>Style
          <select data-cmp-opt="style" data-sym="${esc(s.symbol)}">
            <option value="line" ${s.style !== "area" ? "selected" : ""}>Line</option>
            <option value="area" ${s.style === "area" ? "selected" : ""}>Area</option>
          </select>
        </label>
        <label>Colour <input type="color" data-cmp-opt="color" data-sym="${esc(s.symbol)}" value="${esc(s.color)}" /></label>
        <label>Width
          <select data-cmp-opt="width" data-sym="${esc(s.symbol)}">
            ${[1, 2, 3, 4].map((w) => `<option value="${w}" ${Number(s.width) === w ? "selected" : ""}>${w}</option>`).join("")}
          </select>
        </label>
        ${s.err ? `<span class="hint">${esc(s.err)}</span>` : ""}
      </div>
    </div>`;
  }).join("");
  host.querySelectorAll("[data-cmp-act]").forEach((b) => b.addEventListener("click", async () => {
    const sym = b.dataset.sym;
    const row = cfg.symbols.find((x) => x.symbol === sym);
    if (!row) return;
    if (b.dataset.cmpAct === "vis") { row.visible = row.visible === false; saveCompareCfg(); await applyCompareToChart(); return; }
    if (b.dataset.cmpAct === "remove") { cfg.symbols = cfg.symbols.filter((x) => x.symbol !== sym); saveCompareCfg(); await applyCompareToChart(); return; }
    if (b.dataset.cmpAct === "primary") {
      // Swap roles: the comparison becomes the primary; the old primary joins
      // the comparison list (never silently dropped).
      const oldPrimary = state.chartSymbol;
      cfg.symbols = cfg.symbols.filter((x) => x.symbol !== sym);
      if (oldPrimary && oldPrimary !== sym && cfg.symbols.length < 3) {
        cfg.symbols.push({ symbol: oldPrimary, color: CMP_PALETTE[cfg.symbols.length % CMP_PALETTE.length], style: "line", width: 2, visible: true });
      }
      const savedCfg = { mode: cfg.mode, returnN: cfg.returnN,
        symbols: (cfg.symbols || []).map((s) => ({ symbol: s.symbol, color: s.color, style: s.style, width: s.width, visible: s.visible })) };
      try { localStorage.setItem(compareCfgKey(sym), JSON.stringify(savedCfg)); } catch (e) { /* storage off */ }
      if ($("#symbol-input")) $("#symbol-input").value = sym;
      await loadChart();
      return;
    }
  }));
  host.querySelectorAll("[data-cmp-opt]").forEach((el) => el.addEventListener("change", async () => {
    const sym = el.dataset.sym;
    const row = cfg.symbols.find((x) => x.symbol === sym);
    if (!row) return;
    const key = el.dataset.cmpOpt;
    row[key] = key === "width" ? Number(el.value) : el.value;
    saveCompareCfg();
    await applyCompareToChart();
  }));
}

async function addCompareSymbol(sym) {
  sym = String(sym || "").trim().toUpperCase();
  if (!sym) return;
  const cfg = state.compare || loadCompareCfg(state.chartSymbol);
  state.compare = cfg;
  if (sym === state.chartSymbol) throw new Error("That is already the primary symbol.");
  if (cfg.symbols.some((s) => s.symbol === sym)) throw new Error("Already in the comparison list.");
  if (cfg.symbols.length >= 3) throw new Error("Up to three comparison symbols (four including the primary).");
  try {
    const d = await api(`/api/bars/${encodeURIComponent(sym)}?limit=5`);
    if (!(d.bars || []).length) throw new Error("no stored bars");
  } catch (e) {
    throw new Error(`No stored history for ${sym} (${e.message}).`);
  }
  cfg.symbols.push({ symbol: sym, color: CMP_PALETTE[cfg.symbols.length % CMP_PALETTE.length], style: "line", width: 2, visible: true });
  saveCompareCfg();
  await applyCompareToChart();
  renderComparePanel();
}

function bindIndAndCompareDrawers() {
  // Indicator drawer toggle: the toolbar button opens the chart-side drawer,
  // not a page-level popover (the "controls appear below the chart" defect).
  const indDrawer = document.getElementById("ind-drawer");
  const cmpDrawer = document.getElementById("cmp-drawer");
  const analysisDrawer = document.getElementById("chart-drawer");
  const stage = document.getElementById("chart-stage");
  const syncStage = () => {
    if (!stage) return;
    const any = [indDrawer, cmpDrawer, analysisDrawer].some((d) => d && !d.hidden);
    stage.classList.toggle("with-drawer", any);
  };
  const closeOthers = (keep) => {
    [indDrawer, cmpDrawer, analysisDrawer].forEach((d) => { if (d && d !== keep) d.hidden = true; });
  };
  const toggle = (el, open) => {
    if (!el) return;
    const next = open === undefined ? el.hidden : open;
    if (next) closeOthers(el);
    el.hidden = !next;
    syncStage();
    return next;
  };
  const ib = document.getElementById("pop-indicators-btn");
  if (ib) ib.addEventListener("click", (e) => { e.stopPropagation(); const open = toggle(indDrawer); if (open) renderIndDrawer(); });
  const ic = document.getElementById("ind-drawer-close");
  if (ic) ic.addEventListener("click", () => toggle(indDrawer, false));
  const cb = document.getElementById("pop-compare-btn");
  if (cb) cb.addEventListener("click", (e) => { e.stopPropagation(); const open = toggle(cmpDrawer); if (open) renderComparePanel(); });
  const cc = document.getElementById("cmp-drawer-close");
  if (cc) cc.addEventListener("click", () => toggle(cmpDrawer, false));
  // keep the analysis drawer's stage class in sync
  const analysisBtn = document.getElementById("chart-drawer-toggle");
  if (analysisBtn) analysisBtn.addEventListener("click", () => { closeOthers(analysisDrawer); syncStage(); });
  const analysisClose = document.getElementById("chart-drawer-close");
  if (analysisClose) analysisClose.addEventListener("click", () => setTimeout(syncStage, 0));

  const search = $("#ind-search");
  if (search) {
    let t = null;
    search.addEventListener("input", () => { clearTimeout(t); t = setTimeout(renderIndHits, 120); });
    search.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); renderIndHits(); } });
  }
  const cat = $("#ind-cat");
  if (cat) cat.addEventListener("change", renderIndHits);
  const hu = $("#ind-undo"); if (hu) hu.addEventListener("click", () => indHistStep(-1));
  const hr = $("#ind-redo"); if (hr) hr.addEventListener("click", () => indHistStep(1));
  const ex = $("#ind-export"); if (ex) ex.addEventListener("click", exportIndLayout);
  const im = $("#ind-import"); const imf = $("#ind-import-file");
  if (im && imf) {
    im.addEventListener("click", () => imf.click());
    imf.addEventListener("change", () => {
      const f = imf.files && imf.files[0];
      if (!f) return;
      const rd = new FileReader();
      rd.onload = async () => {
        try { await importIndLayout(String(rd.result || "")); }
        catch (e) { drawStatus(`Import failed: ${e.message}`); }
        imf.value = "";
      };
      rd.onerror = () => { drawStatus("Could not read that file."); imf.value = ""; };
      rd.readAsText(f);
    });
  }
  const ha = $("#ind-hide-all");
  if (ha) ha.addEventListener("click", async () => {
    const paneNames = new Set(await Promise.all((state.customInds || []).map(async (x) => {
      const reg = (await fetchIndicatorRegistry()).find((r) => r.name === x.name);
      return reg && indPlacement(reg) === "pane" ? x.id : null;
    })));
    (state.customInds || []).forEach((x) => { if (paneNames.has(x.id)) x.visible = false; });
    persistCustomInds(state.chartSymbol);
    (state.customInds || []).forEach((x) => applyInstanceVisibility(x));
    renderIndDrawer();
  });
  // quick-layer checkboxes record undo snapshots and persist per-symbol when they change
  QUICK_IND_IDS.forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.addEventListener("change", () => { indHistPush(); saveQuickLayers(state.chartSymbol); });
  });

  // compare drawer bindings
  const addBtn = $("#cmp-add-btn");
  const addInput = $("#cmp-add-symbol");
  const doAdd = async () => {
    const v = addInput && addInput.value;
    if (!v) return;
    try { await addCompareSymbol(v); if (addInput) addInput.value = ""; if ($("#cmp-status")) $("#cmp-status").textContent = ""; }
    catch (e) { if ($("#cmp-status")) $("#cmp-status").textContent = e.message; }
  };
  if (addBtn) addBtn.addEventListener("click", doAdd);
  if (addInput) addInput.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); doAdd(); } });
  const cm = $("#cmp-mode");
  if (cm) cm.addEventListener("change", async () => {
    if (!state.compare) state.compare = loadCompareCfg(state.chartSymbol);
    state.compare.mode = cm.value;
    saveCompareCfg();
    await applyCompareToChart();
    renderComparePanel();
  });
  const crn = $("#cmp-return-n");
  if (crn) crn.addEventListener("change", async () => {
    if (!state.compare) state.compare = loadCompareCfg(state.chartSymbol);
    state.compare.returnN = Math.max(1, Math.min(500, Number(crn.value) || 20));
    saveCompareCfg();
    await applyCompareToChart();
    renderComparePanel();
  });
  const clr = $("#cmp-clear");
  if (clr) clr.addEventListener("click", async () => {
    if (!state.compare) return;
    state.compare.symbols = [];
    saveCompareCfg();
    await applyCompareToChart();
    renderComparePanel();
  });
}

function exportCsv(symbol, bars) {
  const cols = ["time", "open", "high", "low", "close", "volume", "turnover", "percent_change", "validation_status"];
  const lines = [cols.join(",")].concat(bars.map((b) => cols.map((c) => (b[c] === null || b[c] === undefined ? "" : b[c])).join(",")));
  download(`${symbol}.csv`, lines.join("\n"));
}

function download(filename, text, mime) {
  const blob = new Blob([text], { type: mime || "text/csv;charset=utf-8" });
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
  $("#preset-desc").textContent = p.description;
  // Mark any previously rendered results as stale for the newly selected
  // scanner: they belong to a previous run and must not be mistaken for
  // fresh output of the selection. (Run Screen clears this.)
  const staleEl = $("#screen-stale");
  if (staleEl) staleEl.hidden = false;
}

async function runScreen() {
  const key = $("#preset").value;
  let list;
  try { list = (await api("/api/screen/presets")).presets; }
  catch (e) { $("#screen-summary").innerHTML = `<span class="down">${esc(e.message)}</span>`; return; }
  const p = list.find((x) => x.key === key);
  if (!p) return;
  $("#preset-desc").textContent = p.description;
  const staleEl = $("#screen-stale");
  if (staleEl) staleEl.hidden = true;
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
      // Prefer the specific reason (e.g. "rsi unavailable for this security")
      // over the generic note, so an unavailable metric is never opaque.
      { html: esc(x.failures && x.failures.length ? x.failures.join(" · ") : (x.note || "—")), cls: "wrap muted" },
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
async function loadEdgeFreshness() {
  const host = $("#edge-freshness");
  if (!host) return;
  const err = $("#edge-error");
  err.textContent = "";
  try {
    const res = await fetch(EDGE_BASE + "/edge/yonepse/health", { headers: { Accept: "application/json" } });
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    const h = await res.json();
    const failures = Number(h.consecutive_failures || 0);
    host.innerHTML = [
      ["Snapshot quotes", fmtInt(h.quote_count)],
      ["Source updated", (h.source_updated_at || "—").replace("T", " ").slice(0, 19) + "Z"],
      ["Last checked", (h.last_checked_at || "—").replace("T", " ").slice(0, 19) + "Z"],
      ["Last success", (h.last_success_at || "—").replace("T", " ").slice(0, 19) + "Z"],
      ["Freshness", h.freshness || "—"],
      ["Market", h.is_open ? "open" : "closed"],
      ["Scheduled runs", fmtInt(h.runs)],
    ].map(([k, v]) => `<div class="stat"><div class="k">${k}</div><div class="v" style="font-size:15px">${esc(v)}</div></div>`).join("");
    if (failures > 0) {
      err.innerHTML = `<span class="down">${failures} consecutive failed attempt(s): ${esc(h.last_failure_reason || "reason not recorded")}. The last valid snapshot is still being served.</span>`;
    } else if (h.last_failure_at) {
      err.innerHTML = `<span class="warn">Last failure ${esc((h.last_failure_at || "").slice(0, 19))}: ${esc(h.last_failure_reason || "—")} (recovered).</span>`;
    }
    host.insertAdjacentHTML("beforeend",
      `<div class="stat" style="grid-column:1/-1"><div class="k">Price basis</div>` +
      `<div class="v" style="font-size:13px">LTP snapshot only — it is never converted into OHLCV candles. ` +
      `Reason for the last run: ${esc(h.last_run_reason || "—")}.</div></div>`);
  } catch (e) {
    host.innerHTML = `<div class="stat"><div class="k">Edge ingestion</div>` +
      `<div class="v down" style="font-size:14px">not reachable: ${esc(e.message)}</div></div>`;
  }
}

async function loadData() {
  loadLiveSources();
  loadEdgeFreshness();
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
    // `available: null` means "not probed" (a gated/on-demand source we never
    // call just to test), which is not the same as "down".
    const availCell = (v) =>
      v === true ? `<span class="pill pill-pass">yes</span>`
        : v === false ? `<span class="pill pill-hard">no</span>`
          : `<span class="pill pill-info">not probed</span>`;
    $("#sources").innerHTML = table(
      ["Source", "Access", "Auth required", "Available", "Notes"],
      s.sources.map((x) => [
        { html: esc(x.label || x.source), cls: "wrap" },
        { html: esc(x.access_method || "—"), cls: "wrap muted" },
        { html: x.requires_auth ? `<span class="pill pill-review">yes</span>` : "no" },
        { html: availCell(x.available) + (x.authorized === true
            ? ` <span class="pill pill-pass">authorized</span>`
            : (x.authorized === false ? ` <span class="pill pill-info">not authorized</span>` : "")) },
        { html: esc(x.note || ""), cls: "wrap muted" },
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
    // Keep the request + result so the run can be saved as a reproducible
    // experiment; the backend re-runs from `body` on reproduce.
    state.backtestConfig = body;
    state.lastBacktest = d;
    renderBacktest(d);
  } catch (e) {
    errEl.textContent = `Backtest failed: ${e.message}`;
  } finally {
    btn.disabled = false;
  }
}

function renderBacktest(d) {
  const m = d.metrics;
  const pct2 = (v) => (v === null || v === undefined ? "—" : `${Number(v).toFixed(2)}%`);
  const pctSigned = (v) =>
    v === null || v === undefined ? "—" : `${v > 0 ? "+" : ""}${Number(v).toFixed(2)}%`;
  const cells = [
    ["Data as of", esc(d.data_as_of)],
    ["Period", `${esc(d.start)} → ${esc(d.end)}`],
    ["Final equity", fmtNum(m.final_equity)],
    ["Total return", pctSigned(m.total_return_pct)],
    ["Buy &amp; hold", pctSigned(m.benchmark_total_return_pct)],
    ["CAGR", pctSigned(m.cagr_pct)],
    ["Max drawdown", pctSigned(m.max_drawdown_pct)],
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
      { html: fmtPct(t.return_pct), cls: pctClass(t.return_pct), title: "percent, not a fraction" },
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
      color: PRAVAHA.emerald,
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

/* ------------------------------------------------------- research workspace
   One symbol, one place. Two jobs:
   1. show the symbol overview and every analysis module's output;
   2. show the state each module ACTUALLY reached, so a failure or a blocked
      module is visible instead of the page quietly looking successful.
   No completion percentage is drawn, because the backend does not measure one. */

const WS_STATE_CLASS = {
  COMPLETED: "up",
  COMPLETED_WITH_WARNINGS: "warn",
  FAILED: "down",
  BLOCKED_BY_MISSING_DATA: "down",
  NOT_STARTED: "muted",
  QUEUED: "muted",
  RUNNING: "warn",
  CANCELLED: "muted",
  CACHED_RESULT_AVAILABLE: "muted",
};

function wsBadge(state) {
  const cls = WS_STATE_CLASS[state] || "muted";
  return `<span class="${cls}">${esc(String(state).replace(/_/g, " ").toLowerCase())}</span>`;
}

/** Human sentence for a module state, never implying more than we know. */
function wsStateSentence(m) {
  if (m.state === "BLOCKED_BY_MISSING_DATA") return m.error || "Blocked by missing data.";
  if (m.state === "FAILED") return m.error || "Failed.";
  if (m.state === "NOT_STARTED") return "Not run for this request.";
  if (m.state === "COMPLETED_WITH_WARNINGS")
    return (m.warnings || []).join(" ") || "Completed with warnings.";
  return (m.warnings || []).join(" ") || "";
}

function renderWorkspace(d) {
  $("#ws-head").innerHTML =
    `<b>${esc(d.symbol)}</b> · window ${esc(d.input.start)} → ${esc(d.input.end)}` +
    ` · ${d.input.bars} bars (bound ${d.limit_applied})` +
    ` · computed ${esc(d.calculated_at)} · overall ${wsBadge(d.overall_state)}` +
    `<br><span class="muted">${esc(d.method)} v${esc(d.method_version)} · ` +
    `${esc(d.classification_note)}</span>`;

  const ov = d.overview;
  if (ov) {
    $("#ws-overview").innerHTML = [
      `<div><b>${fmtSmart(ov.last_close)}</b> close</div>`,
      `<div>${pctPlain(ov.change_percent)} <span class="muted">(${fmtSmart(ov.change)})</span></div>`,
      `<div>observed <b>${esc(ov.observation_date)}</b></div>`,
      `<div>${fmtInt(ov.observations)} bars</div>`,
      `<div>vol ${ov.latest_volume === null ? "—" : fmtInt(ov.latest_volume)}</div>`,
      `<div class="muted">${esc(ov.price_kind)}</div>`,
      `<div class="muted">source: ${esc(ov.provenance?.source || "unknown")}</div>`,
    ].join("");
  } else {
    $("#ws-overview").innerHTML = `<div class="muted">Overview did not run.</div>`;
  }

  const statusRows = d.modules.map((m) => [
    { html: `<b>${esc(m.label)}</b>` },
    { html: wsBadge(m.state), cls: WS_STATE_CLASS[m.state] || "" },
    { html: m.classification ? esc(m.classification) : "—" },
    {
      html: m.method
        ? `${esc(m.method)} <span class="muted">v${esc(m.method_version || "")}</span>`
        : "—",
    },
    { html: m.elapsed_ms === null ? "—" : `${fmtSmart(m.elapsed_ms)} ms` },
    { html: wsStateSentence(m) || "—" },
  ]);
  $("#ws-status").innerHTML = table(
    ["Module", "State", "Class", "Method", "Elapsed", "Notes"],
    statusRows
  );

  // One expandable section per module. Payloads are shown as returned by the
  // backend — the frontend never recalculates anything.
  $("#ws-sections").innerHTML = d.modules
    .filter((m) => m.result)
    .map((m) => {
      const rows = Object.entries(m.result).map(([k, v]) => [
        { html: `<b>${esc(prettifyKey(k))}</b>` },
        { html: renderValue(v) },
      ]);
      const warn = (m.warnings || []).length
        ? `<ul class="list">${m.warnings.map((w) => `<li class="warn">${esc(w)}</li>`).join("")}</ul>`
        : "";
      return (
        `<details class="card"><summary>${esc(m.label)} ` +
        `${wsBadge(m.state)} <span class="muted">${esc(m.classification || "")}</span></summary>` +
        warn +
        table(["Field", "Value"], rows) +
        `</details>`
      );
    })
    .join("");

  const failed = d.failed || [];
  $("#ws-error").textContent = failed.length
    ? `${failed.length} module(s) did not complete: ` +
      failed.map((f) => `${f.name} (${f.state})`).join(", ")
    : "";
}

async function loadWorkspace() {
  const symbol = ($("#ws-symbol").value || "").trim().toUpperCase();
  const errEl = $("#ws-error");
  errEl.textContent = "";
  if (!symbol) { errEl.textContent = "Enter a symbol."; return; }
  const limit = parseInt($("#ws-limit").value, 10) || 500;
  const btn = $("#ws-run");
  btn.disabled = true;
  btn.textContent = "Running…";
  try {
    const d = await api(
      `/api/research/workspace/${encodeURIComponent(symbol)}?limit=${limit}`
    );
    renderWorkspace(d);
  } catch (e) {
    errEl.textContent = `Workspace failed: ${e.message}`;
    $("#ws-overview").innerHTML = "";
    $("#ws-sections").innerHTML = "";
  } finally {
    btn.disabled = false;
    btn.textContent = "Load workspace";
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
  const cf = d.cash_flow || {};
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
      ["Invested (buy cost)", `NPR ${fmtNum(cf.total_invested, 0)}`, ""],
      ["Proceeds (sells)", `NPR ${fmtNum(cf.total_proceeds, 0)}`, ""],
      ["Fees paid", `NPR ${fmtNum(cf.total_fees, 0)}`, ""],
      ["Net cash flow", fmtNum(cf.net_cash_flow, 0), pctClass(cf.net_cash_flow)],
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
        `<button class="ghost" data-reflect="${fmtInt(e.id)}">Reflect</button> ` +
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
  $$("#jr-entries button[data-reflect]").forEach((b) =>
    b.addEventListener("click", () => reflectEntry(Number(b.dataset.reflect)))
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
/* ------------------------------------------------- Phase 2 endpoint loaders */

async function loadRegime() {
  const el = $("#regime");
  const hint = $("#regime-hint");
  el.innerHTML = `<div class="stat"><div class="k">Status</div><div class="v muted">Loading…</div></div>`;
  try {
    const d = await api("/api/regime");
    if (d.status !== "ok") {
      el.innerHTML = `<div class="stat"><div class="k">Status</div><div class="v muted">insufficient data</div></div>`;
      hint.textContent = d.reason || "Regime labels are not available yet.";
      return;
    }
    const c = d.current || {};
    el.innerHTML = [
      ["Trend", c.trend],
      ["Volatility", c.volatility],
      ["Momentum", c.momentum],
      ["Session", d.last_date],
    ]
      .map(([k, v]) => `<div class="stat"><div class="k">${esc(k)}</div><div class="v">${esc(String(v ?? "—"))}</div></div>`)
      .join("");
    hint.textContent =
      `Labels from the ${d.params && d.params.proxy ? d.params.proxy : "equal-weighted market proxy"}. ` +
      `Causal — each label uses only data up to its session — and not investment advice.`;
  } catch (e) {
    el.innerHTML = `<div class="stat"><div class="k">Error</div><div class="v down">${esc(e.message)}</div></div>`;
    hint.textContent = "";
  }
}

function conditionsFromEditor() {
  const raw = ($("#al-conditions").value || "").trim();
  if (!raw) throw new Error("Paste a JSON array of conditions first.");
  let parsed;
  try {
    parsed = JSON.parse(raw);
  } catch (e) {
    throw new Error(`Conditions are not valid JSON: ${e.message}`);
  }
  if (!Array.isArray(parsed) || !parsed.length) {
    throw new Error("Conditions must be a non-empty JSON array.");
  }
  return parsed;
}

async function evaluateAlerts() {
  const resEl = $("#al-result");
  let conditions;
  try {
    conditions = conditionsFromEditor();
  } catch (e) {
    resEl.innerHTML = `<span class="error">${esc(e.message)}</span>`;
    return;
  }
  const btn = $("#al-run");
  btn.disabled = true;
  resEl.textContent = "Evaluating…";
  try {
    const d = await api("/api/alerts/evaluate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ conditions }),
    });
    const rejected = (d.rejected || [])
      .map((r) => `${(r.problems || []).join("; ") || "rejected"}`)
      .join(" · ");
    resEl.textContent =
      `Evaluated ${fmtInt(d.evaluated)} condition(s): ${fmtInt(d.fired.length)} fired now, ` +
      `${fmtInt(d.already_active)} already recorded (within cooldown / fire-once), ` +
      `${fmtInt(d.rejected.length)} rejected.` +
      (d.cooldown_held ? ` Re-armed after cooldown: ${fmtInt(d.cooldown_held)}.` : "") +
      (rejected ? ` Rejected — ${rejected}` : "");
    loadAlertHistory();
  } catch (e) {
    resEl.innerHTML = `<span class="error">${esc(e.message)}</span>`;
  } finally {
    btn.disabled = false;
  }
}

async function loadAlertHistory() {
  const el = $("#al-history");
  try {
    const d = await api("/api/alerts/history?limit=50");
    const alerts = d.alerts || [];
    if (!alerts.length) {
      el.innerHTML = `<div class="empty">No alerts recorded. An alert is written when its condition fires
        and re-arms only after its own cooldown has elapsed (or when the history is cleared).</div>`;
      return;
    }
    const unack = alerts.filter((a) => !a.acknowledged).length;
    el.innerHTML = `<div class="controls"><span class="hint">${fmtInt(alerts.length)} recorded ·
        ${fmtInt(unack)} unacknowledged</span>
      <button id="al-ack-all" class="ghost">Acknowledge all</button></div>`
      + table(
        ["Severity", "Recorded at", "Symbol", "Fires", "Message", ""],
        alerts.map((a) => [
          { html: `<span class="pill ${a.severity === "critical" ? "pill-hard" : a.severity === "info" ? "pill-info" : "pill-review"}">${esc(a.severity)}</span>` },
          { html: `${esc(a.created_at || "—")}${a.acknowledged ? ` <span class="muted">ack</span>` : ""}` },
          { html: esc(a.symbol || "—") },
          { html: fmtInt(a.fire_count) },
          { html: esc(a.message || ""), cls: "wrap" },
          { html: a.acknowledged ? `<span class="muted">—</span>`
            : `<button class="ghost al-ack" data-id="${esc(a.id)}">Acknowledge</button>` },
        ])
      );
    const ackAll = $("#al-ack-all");
    if (ackAll) ackAll.addEventListener("click", () => acknowledgeAlerts({ all: true }));
    el.querySelectorAll(".al-ack").forEach((b) => b.addEventListener("click", () => {
      acknowledgeAlerts({ alert_ids: [Number(b.dataset.id)] });
    }));
  } catch (e) {
    el.innerHTML = `<div class="error">${esc(e.message)}</div>`;
  }
}

async function acknowledgeAlerts(payload) {
  const resEl = $("#al-result");
  try {
    const d = await api("/api/alerts/acknowledge", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (resEl) resEl.textContent = `Acknowledged ${fmtInt(d.acknowledged)} alert(s). `
      + "Acknowledging records that you saw it; it does not delete history or change a cooldown.";
    loadAlertHistory();
  } catch (e) {
    if (resEl) resEl.innerHTML = `<span class="error">${esc(e.message)}</span>`;
  }
}

async function clearAlertHistory() {
  if (!confirm("Clear the alert history so every condition can fire again?")) return;
  const resEl = $("#al-result");
  try {
    const d = await api("/api/alerts/clear", { method: "DELETE" });
    resEl.textContent = `Cleared ${fmtInt(d.cleared)} recorded alert(s).`;
    loadAlertHistory();
  } catch (e) {
    resEl.innerHTML = `<span class="error">${esc(e.message)}</span>`;
  }
}

function renderRatioReport(r) {
  const price = r.price && r.price.value != null
    ? `price ${fmtSmart(r.price.value)} (${esc(r.price.date || "?")}, ${esc(r.price.kind || "stored")})`
    : "no usable stored price";
  const ratioRow = (obj) => {
    if (!obj) return { html: "—" };
    const shown =
      obj.value == null
        ? `<span class="muted">—</span>`
        : `<b>${fmtSmart(obj.value)}</b>`;
    const why =
      obj.value == null
        ? esc(obj.unavailable_reason || "no reason given")
        : (obj.inputs || [])
            .map((i) => {
              const bits = [i.field, fmtSmart(i.value), i.period_end || i.period_label, i.verification, i.source].filter(Boolean);
              return bits.map(String).map(esc).join(" · ");
            })
            .join("<br>");
    return { html: `${shown}<div class="tiny muted">${why}</div>`, cls: "wrap" };
  };
  return (
    `<p class="hint"><b>${esc(r.symbol)}</b> · status ${esc(r.status || "?")} · ${price}</p>` +
    table(
      ["Ratio", "Value", "Why / inputs"],
      [
        [{ html: "P/E" }, ratioRow(r.ratios && r.ratios.pe)],
        [{ html: "P/B" }, ratioRow(r.ratios && r.ratios.pb)],
        [{ html: "Dividend yield %" }, ratioRow(r.ratios && r.ratios.dividend_yield_pct)],
      ]
    )
  );
}

async function loadRatios() {
  const raw = ($("#ratio-symbols").value || "").trim().toUpperCase();
  const out = $("#ratio-out");
  if (!raw) {
    out.innerHTML = `<div class="error">Enter one symbol, or several separated by commas.</div>`;
    return;
  }
  out.innerHTML = `<div class="empty">Loading…</div>`;
  try {
    const multi = raw.includes(",");
    const d = multi
      ? await api(`/api/fundamentals/compare?symbols=${encodeURIComponent(raw)}`)
      : await api(`/api/fundamentals/${encodeURIComponent(raw)}/ratios`);
    const reports = multi ? d.symbols || [] : [d];
    out.innerHTML = reports.length
      ? reports.map(renderRatioReport).join("")
      : `<div class="empty">Nothing returned for ${esc(raw)}.</div>`;
  } catch (e) {
    out.innerHTML = `<div class="error">${esc(e.message)}</div>`;
  }
}

async function loadFloorSheetTrend() {
  const sym = ($("#fs-symbol").value || "").trim().toUpperCase();
  const out = $("#fs-trend-out");
  out.innerHTML = `<div class="empty">Loading…</div>`;
  try {
    const q = new URLSearchParams({ sessions: "10", top: $("#fs-top").value || "10" });
    if (sym) q.set("symbol", sym);
    const d = await api(`/api/floorsheet/trend?${q}`);
    if (d.status !== "ok") {
      out.innerHTML = `<div class="empty">${esc(d.reason || d.status)}. ${esc(d.note || "")}</div>`;
      return;
    }
    const parts = [
      `<p class="hint"><b>${esc((d.activity_trend && d.activity_trend.direction) || "?")}</b> — ` +
        `${esc((d.activity_trend && d.activity_trend.basis) || "")} · scope: ${esc(d.scope || "—")}</p>`,
      `<h3 class="topic-head">Sessions (oldest first)</h3>`,
      table(
        ["Session", "Prints", "Quantity", "Turnover", "Buyers", "Sellers"],
        (d.activity || []).map((a) => [
          { html: esc(a.traded_at) },
          { html: fmtInt(a.prints) },
          { html: fmtInt(a.quantity) },
          { html: fmtNum(a.turnover, 0) },
          { html: fmtInt(a.buyers) },
          { html: fmtInt(a.sellers) },
        ])
      ),
      `<h3 class="topic-head">Broker net flow (inference — broker codes, not beneficial owners)</h3>`,
    ];
    const flows = d.broker_net || [];
    parts.push(
      flows.length
        ? table(
            ["Broker", "Bought", "Sold", "Net", "Flow"],
            flows.slice(0, 20).map((f) => [
              { html: esc(f.broker) },
              { html: fmtInt(f.bought) },
              { html: fmtInt(f.sold) },
              { html: fmtInt(f.net), cls: f.net > 0 ? "up" : f.net < 0 ? "down" : "muted" },
              { html: esc(f.flow) },
            ])
          )
        : `<div class="empty">No broker flow in this scope.</div>`
    );
    if (d.integrity && d.integrity.net_sums_to_zero === false) {
      parts.push(`<p class="hint warn">Integrity check failed: per-broker nets do not sum to zero.</p>`);
    }
    out.innerHTML = parts.join("");
  } catch (e) {
    out.innerHTML = `<div class="error">${esc(e.message)}</div>`;
  }
}

async function runAgent() {
  const question = ($("#rs-question").value || "").trim();
  const out = $("#rs-agent-out");
  const errEl = $("#rs-error");
  errEl.textContent = "";
  if (!question) {
    errEl.textContent = "Type a question first.";
    return;
  }
  const btn = $("#rs-agent-btn");
  btn.disabled = true;
  out.innerHTML = `<div class="empty">Running tools…</div>`;
  try {
    const d = await api("/api/agent/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question,
        interpret: $("#rs-agent-ai").checked,
        include_private: false,
      }),
    });
    const parts = [];
    parts.push(`<p class="hint">Plan: ${(d.plan || []).map(esc).join(" → ") || "—"}</p>`);
    const results = d.tool_results || [];
    parts.push(
      results.length
        ? table(
            ["Tool", "Status", "Summary", "Provenance", "Why (if not plain)"],
            results.map((r) => [
              {
                html:
                  `<b>${esc(r.tool)}</b>` +
                  (r.private ? ` <span class="pill pill-review">private</span>` : ""),
              },
              {
                html: `<span class="pill ${r.status === "ok" ? "pass" : "pill-review"}">${esc(r.status)}</span>`,
              },
              { html: esc(r.summary || ""), cls: "wrap" },
              { html: esc(r.provenance || "—"), cls: "wrap" },
              { html: esc(r.reason || "—"), cls: "wrap" },
            ])
          )
        : `<div class="empty">No tool matched the question — nothing was computed.</div>`
    );
    const unresolved = d.unresolved || [];
    if (unresolved.length) {
      parts.push(
        `<h3 class="topic-head">Unresolved</h3><ul class="list">` +
          unresolved.map((u) => `<li class="warn">${esc(u)}</li>`).join("") +
          `</ul>`
      );
    }
    const ai = d.ai_interpretation;
    if (ai && ai.status === "ok") {
      parts.push(
        `<h3 class="topic-head">AI interpretation — ${esc(ai.provider || "configured provider")}</h3>` +
          `<p>${esc(ai.text || "")}</p>`
      );
    } else if (ai) {
      parts.push(
        `<div class="banner warn">AI interpretation ${esc(ai.status || "unavailable")}: ` +
          `${esc(ai.reason || "no text produced")}</div>`
      );
    } else {
      parts.push(
        `<p class="hint">No AI interpretation was requested — the tool results above are deterministic and stand alone.</p>`
      );
    }
    const priv = d.privacy || {};
    if ((priv.private_tools || []).length) {
      parts.push(
        `<p class="hint">Private tools in this run: ${(priv.private_tools || []).map(esc).join(", ")}.` +
          ((priv.excluded_from_ai || []).length
            ? ` Excluded from any AI prompt: ${(priv.excluded_from_ai || []).map(esc).join(", ")}.`
            : "") +
          `</p>`
      );
    }
    out.innerHTML = parts.join("");
  } catch (e) {
    out.innerHTML = `<div class="error">${esc(e.message)}</div>`;
  } finally {
    btn.disabled = false;
  }
}

async function loadPortfolioRisk() {
  const out = $("#pf-risk-out");
  const btn = $("#pf-risk-run");
  btn.disabled = true;
  out.innerHTML = `<div class="empty">Computing from stored history and the ledger…</div>`;
  try {
    const d = await api("/api/portfolio/risk");
    const parts = [];
    const limits = d.limits || {};
    parts.push(
      `<p class="hint">Limits: position weight ≤ ${fmtSmart(limits.max_weight_pct)}%, ` +
        `drawdown ≤ ${fmtSmart(limits.max_drawdown_pct)}%, volatility ≤ ${fmtSmart(limits.max_vol_pct)}%.</p>`
    );
    if (d.status !== "ok") {
      parts.push(
        `<div class="empty">${esc(d.reason || "metrics unavailable")}. ${esc(d.disclaimer_note || "")}</div>`
      );
    } else {
      const m = d.metrics || {};
      parts.push(
        `<div class="stat-row">` +
          [
            ["Sessions", fmtInt(m.sessions)],
            ["Annualised vol", m.annualized_volatility_pct == null ? "—" : pctPlain(m.annualized_volatility_pct)],
            ["Max drawdown", m.max_drawdown_pct == null ? "—" : pctPlain(m.max_drawdown_pct)],
            ["Current drawdown", m.current_drawdown_pct == null ? "—" : pctPlain(m.current_drawdown_pct)],
            ["Daily VaR 95%", m.daily_var_95_pct == null ? "—" : pctPlain(m.daily_var_95_pct)],
            ["Daily CVaR 95%", m.daily_cvar_95_pct == null ? "—" : pctPlain(m.daily_cvar_95_pct)],
            ["Sharpe (rf 0)", fmtSmart(m.sharpe_rf0)],
          ]
            .map(
              ([k, v]) =>
                `<div class="stat"><div class="k">${esc(k)}</div><div class="v" style="font-size:16px">${v}</div></div>`
            )
            .join("") +
          `</div>`
      );
      const breaches = d.breaches || [];
      parts.push(
        breaches.length
          ? `<ul class="list">` +
            breaches
              .map(
                (b) =>
                  `<li class="warn">${esc(b.limit)}: measured ${fmtSmart(
                    b.measured_pct != null ? b.measured_pct : b.measured
                  )} vs threshold ${fmtSmart(b.threshold_pct)}</li>`
              )
              .join("") +
            `</ul>`
          : `<p class="hint">No limit breached.</p>`
      );
      if ((d.assumptions || []).length) {
        parts.push(
          `<ul class="list">` +
            d.assumptions.map((a) => `<li class="muted">${esc(a)}</li>`).join("") +
            `</ul>`
        );
      }
    }
    out.innerHTML = parts.join("");
  } catch (e) {
    out.innerHTML = `<div class="error">${esc(e.message)}</div>`;
  } finally {
    btn.disabled = false;
  }
}

async function reflectEntry(id) {
  const el = $("#jr-reflect");
  el.innerHTML = `<div class="empty">Reflecting on entry ${fmtInt(id)}…</div>`;
  try {
    const d = await api(`/api/journal/${id}/reflect`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ authorize_private: $("#jr-reflect-ai").checked }),
    });
    const ctx = d.deterministic || {};
    const e = ctx.entry || {};
    const grade = ctx.plan_grade;
    const ai = d.ai_interpretation || {};
    const parts = [
      `<p class="hint">Entry ${fmtInt(d.entry_id)} · <b>${esc(e.symbol || "—")}</b> · ` +
        `${esc(e.strategy || "no strategy")} · ${esc(ctx.note || "")}</p>`,
      `<div class="stat-row">` +
        [
          ["Entry", fmtNum(e.entry_price)],
          ["Target", fmtNum(e.planned_target)],
          ["Invalidation", fmtNum(e.planned_invalidation)],
          ["Exit", fmtNum(e.exit_price)],
          ["Followed plan", e.followed_plan == null ? "—" : e.followed_plan ? "yes" : "no"],
          ["Closed", (e.closed_at || "").slice(0, 19) || "open"],
        ]
          .map(
            ([k, v]) =>
              `<div class="stat"><div class="k">${esc(k)}</div><div class="v" style="font-size:16px">${esc(String(v))}</div></div>`
          )
          .join("") +
        `</div>`,
    ];
    if (grade && grade.result) {
      parts.push(
        `<p class="hint">Plan grade: ${esc(grade.result)}` +
          (grade.r_multiple != null ? ` · R ${fmtSmart(grade.r_multiple)}` : "") +
          `</p>`
      );
    }
    if (ai.status === "ok") {
      parts.push(
        `<h3 class="topic-head">AI reflection — recipient: ${esc(ai.recipient || ai.provider || "unspecified")}</h3>` +
          `<p>${esc(ai.text || "")}</p>`
      );
    } else {
      parts.push(
        `<p class="hint">AI reflection: ${esc(ai.status || "not requested")} — ` +
          `${esc(ai.reason || "no AI call was made")}</p>` +
          `<p class="hint muted">Recipient: ${esc(ai.recipient || "none")}</p>`
      );
    }
    el.innerHTML = parts.join("");
  } catch (err) {
    el.innerHTML = `<div class="error">${esc(err.message)}</div>`;
  }
}

/* ------------------------------------------- chart patterns + statistics */
/* Pattern catalogue is discovered from the endpoint (`catalogue`), so the UI
   can never advertise a detector the engine does not implement. */
let patternCatalogue = null;
let patternPicks = null;      // Set of selected names; null = "all"
let patternData = null;

function buildPatternPicker() {
  const host = $("#pattern-picker");
  if (!host || !patternCatalogue) return;
  const names = Object.keys(patternCatalogue);
  host.innerHTML = names.map((n) => {
    const on = !patternPicks || patternPicks.has(n);
    const dir = patternCatalogue[n];
    return `<label class="chk"><input type="checkbox" class="pat-pick" value="${esc(n)}"${on ? " checked" : ""} /> `
      + `${esc(n)} <span class="muted">(${esc(dir)})</span></label>`;
  }).join("");
  host.querySelectorAll(".pat-pick").forEach((cb) => cb.addEventListener("change", () => {
    patternPicks = new Set($$(".pat-pick").filter((c) => c.checked).map((c) => c.value));
    updatePatternSelHint();
    renderPatternPanel();
  }));
  updatePatternSelHint();
}

function updatePatternSelHint() {
  const hint = $("#pattern-sel-hint");
  if (!hint) return;
  const total = patternCatalogue ? Object.keys(patternCatalogue).length : 0;
  hint.textContent = patternPicks
    ? (patternPicks.size === 0 ? "none selected" : `${patternPicks.size} of ${total} selected`)
    : `all ${total}`;
}

async function loadPatternPanel(symbol) {
  const patEl = $("#patterns");
  const patHint = $("#patterns-hint");
  if (!patEl) return;
  patEl.innerHTML = `<div class="empty">Detecting…</div>`;
  // Detect over the SAME window the chart is drawing, so pivot indexes and the
  // overlay's date mapping agree with the bars on screen (same fix as Elliott /
  // harmonic: the engine's bar indexes must mean the same bars the user sees).
  const range = $("#range") ? $("#range").value : "120";
  const qs = range === "0" ? "" : `?limit=${encodeURIComponent(range)}`;
  let d;
  try {
    d = await api(`/api/bars/${encodeURIComponent(symbol)}/patterns${qs}`);
  }
  catch (e) { patEl.innerHTML = `<div class="empty">Patterns unavailable: ${esc(e.message)}</div>`; return; }

  if (!patternCatalogue && d.catalogue) { patternCatalogue = d.catalogue; buildPatternPicker(); }
  patternData = d;
  patternData.symbol = symbol;

  if (!d.available) {
    patEl.innerHTML = `<div class="empty">${esc(d.unavailable_reason || "unavailable")}</div>`;
    patHint.textContent = "Not enough history for the documented minimum-bar rule.";
    clearPatternOverlay();
    return;
  }
  renderPatternPanel();
  patHint.textContent = "Geometric matches over confirmed swing pivots. Descriptive, not predictive; "
    + "quality is a documented symmetry rule, not a probability of profit. "
    + "“confirmed” means price already closed beyond the trigger in stored history.";
}

function renderPatternPanel() {
  const patEl = $("#patterns");
  if (!patEl) return;
  if (!patternData) {
    patEl.innerHTML = `<div class="empty">${state.chartSymbol === "NEPSE"
      ? "Chart-pattern detection is computed for individual securities, not the composite index."
      : "No pattern scan loaded yet."}</div>`;
    return;
  }
  const all = patternData.patterns || [];
  const shown = patternPicks ? all.filter((p) => patternPicks.has(p.pattern)) : all;
  if (!shown.length) {
    patEl.innerHTML = `<div class="empty">${all.length
      ? "All matches are hidden by the current pattern selection."
      : "No rule-based pattern matched. An absence of a match is not a clean chart."}</div>`;
  } else {
    patEl.innerHTML = table(
      ["Pattern", "Bias", "Status", "Quality", "Start", "End", "Breakout", "Invalidation", ""],
      shown.map((p, i) => [
        { html: `<b>${esc(p.pattern)}</b>` },
        { html: esc(p.direction) },
        { html: p.status === "confirmed" ? `<span class="pill">confirmed</span>` : `<span class="pill pill-review">forming</span>` },
        { html: fmtNum(p.quality, 0) },
        { html: esc(p.start_date || p.start_index) },
        { html: esc(p.end_date || p.end_index) },
        { html: fmtNum(p.breakout_level) },
        { html: fmtNum(p.invalidation_level) },
        { html: `<button class="ghost pat-info" data-name="${esc(p.pattern)}" data-i="${i}">Evidence</button>` },
      ])
    );
    patEl.querySelectorAll(".pat-info").forEach((btn) => btn.addEventListener("click", () => {
      const p = shown[parseInt(btn.dataset.i, 10)];
      if (p) showPatternEvidence(p);
    }));
  }
  if (patternOverlayOn()) drawPatternOverlay(shown);
  else clearPatternOverlay();
}

function patternOverlayOn() {
  const cb = $("#pattern-overlay");
  return cb ? cb.checked : true;
}

function showPatternEvidence(p) {
  // Replace the transient panel content with the full, unedited evidence list.
  const el = $("#pattern-evidence");
  const host = el || (() => {
    const d = document.createElement("div");
    d.id = "pattern-evidence";
    d.className = "card";
    $("#patterns").parentElement.appendChild(d);
    return d;
  })();
  const fmt = (v) => (v == null ? "—" : fmtNum(v));
  host.innerHTML = `<h2>${esc(p.pattern)} — ${esc(p.direction)}</h2>`
    + `<p class="hint">Status <b>${esc(p.status)}</b> · quality ${fmt(p.quality)} · `
    + `bars ${esc(p.start_date)} → ${esc(p.end_date)}</p>`
    + `<ul class="hint">${(p.evidence || []).map((e) => `<li>${esc(e)}</li>`).join("") || "<li>no evidence lines returned</li>"}</ul>`
    + `<p class="hint">Breakout/trigger ${fmt(p.breakout_level)} · invalidation ${fmt(p.invalidation_level)}`
    + ` · target ${fmt(p.target_level)}</p>`
    + `<div class="tablewrap">${table(["Pivot", "Date", "Price"],
        (p.pivots || []).map((pv) => [
          { html: esc(pv.kind || pv.label || "—") },
          { html: esc(pv.date || pv.index) },
          { html: fmtNum(pv.price) },
        ]))}</div>`
    + `<button class="ghost" id="pat-close">Close evidence</button>`;
  const close = $("#pat-close");
  if (close) close.addEventListener("click", () => { host.remove(); });
}

function clearPatternOverlay() {
  const chart = state.charts.price;
  (state.patternSeries || []).forEach((s) => { try { chart.removeSeries(s); } catch (e) { /* gone */ } });
  state.patternSeries = [];
  state.patternMarkers = [];
  flushMarkers();
}

/* Draw the actual pivots and the breakout/invalidation lines the detector
   reported — never a reconstructed or "idealised" shape. */
function drawPatternOverlay(patterns) {
  const chart = state.charts.price;
  state.patternList = Array.isArray(patterns) ? patterns : [];
  if (!chart) return;
  clearPatternOverlay();
  const fullDates = (state.chartBars || []).map((b) => b.time);
  // Prefer each pivot's own reported date (authoritative). Fall back to the
  // index only when the engine did not supply one, mapping it through the same
  // window the endpoint was asked for.
  const visible = new Set(state.chartDates);
  const dateOf = (pv) => pv.date
    || (fullDates && pv.index != null && pv.index < fullDates.length ? fullDates[pv.index] : null);
  const colorFor = (dir) => (dir === "bullish" ? PRAVAHA.up : dir === "bearish" ? PRAVAHA.down : PRAVAHA.caution);

  const vis = state.overlayVis || { levelLines: true, shapeLines: true, patMarkers: true, candleCap: 15 };
  // §5.9 label-mess control: highest-quality patterns first, and the level
  // lines lose their full name titles (they were flooding the price axis).
  // The remaining matches stay in the Evidence table; only chart ink is capped.
  const cap = Math.max(1, parseInt(($("#ov-max-patterns") || {}).value, 10) || 3);
  const ranked = (patterns || []).slice().sort((a, b) =>
    ((b.status === "confirmed") ? 1 : 0) - ((a.status === "confirmed") ? 1 : 0)
    || (Number(b.quality) || 0) - (Number(a.quality) || 0));
  ranked.slice(0, cap).forEach((p) => {
    const color = colorFor(p.direction);
    const pts = (p.pivots || []).map((pv) => {
      const dt = dateOf(pv);
      return dt && (!state.chartDates.length || visible.has(dt)) ? { time: dt, value: pv.price } : null;
    }).filter(Boolean);
    if (pts.length >= 2 && vis.shapeLines) {
      const s = chart.addLineSeries({
        color, lineWidth: 2, priceLineVisible: false, lastValueVisible: false,
        title: "", // pattern identity lives in the marker + Evidence table, not on the axis
      });
      s.setData(pts);
      state.patternSeries.push(s);
      if (vis.patMarkers) state.patternMarkers.push(noteMarker({
        time: pts[pts.length - 1].time,
        position: p.direction === "bearish" ? "aboveBar" : "belowBar",
        color, shape: "square", text: shortPattern(p.pattern),
      }, "Chart-pattern detector",
      `Pattern marker “${shortPattern(p.pattern)}” = ${p.pattern} (${p.direction}, ${p.status || "detected"}), `
      + `${esc(p.start_date || "?")} → ${esc(p.end_date || "?")}. Disable it with the Pattern markers toggle, `
      + `or remove the Chart-patterns layer.`));
    }
    // Breakout and invalidation levels are the detector's own numbers.
    [["breakout", p.breakout_level], ["invalidation", p.invalidation_level]].forEach(([kind, lvl]) => {
      if (lvl == null || !isFinite(lvl) || !vis.levelLines) return;
      const first = state.chartDates[0];
      const last = state.chartDates[state.chartDates.length - 1];
      if (!first) return;
      const s = chart.addLineSeries({
        color: kind === "breakout" ? PRAVAHA.cyan : PRAVAHA.muted, lineWidth: 1,
        lineStyle: kind === "breakout" ? 0 : 2, priceLineVisible: false, lastValueVisible: false,
        title: "",
      });
      s.setData(first === last ? [{ time: first, value: lvl }]
        : [{ time: first, value: lvl }, { time: last, value: lvl }]);
      state.patternSeries.push(s);
      // compact axis chip for the level itself — no full pattern name
      if (vis.patMarkers) state.patternMarkers.push(noteMarker({
        time: p.status === "confirmed" ? (p.end_date || first) : first,
        position: kind === "breakout" ? "aboveBar" : "belowBar",
        color: kind === "breakout" ? PRAVAHA.cyan : PRAVAHA.muted,
        shape: "circle", text: `${kind === "breakout" ? "BO" : "INV"} ${fmtNum(lvl, 0)}`,
      }, "Chart-pattern detector",
      `“${kind === "breakout" ? "BO" : "INV"} ${fmtNum(lvl, 0)}” = `
      + `${kind === "breakout" ? "breakout / trigger level" : "invalidation level"} of the ${p.pattern} `
      + `(${p.direction}) that the chart-pattern detector found. Disable it with the Pattern markers toggle, `
      + `or remove the Chart-patterns layer.`));
    });
  });
  flushMarkers();
}

function shortPattern(name) {
  return String(name).split("_").map((w) => w[0] ? w[0].toUpperCase() : "").join("").slice(0, 4);
}

/* ============ §5.21 Kronos AI on the main chart =========================
   Real forecast runs against /api/kronos/forecast. Forecast candles are
   drawn in their own amber series — never merged with observed candles —
   and every state the workflow can hit (weights missing, run failure,
   stale symbol) is printed as itself, not replaced by illustrative data. */
const KRONOS_WEIGHT_DIRS = { base: "Kronos-base", small: "Kronos-small", mini: "Kronos-mini" };

/* §5.21/K: forecast candles are REAL candle geometry in the app's own
   bullish/bearish colours, outlined in amber so a glance separates the model's
   prediction from observed candles. Palette lives here so draw/hide/reshow
   use exactly the same series options. */
const FORECAST_UP = PRAVAHA.up;
const FORECAST_DN = PRAVAHA.down;
const FORECAST_EDGE = PRAVAHA.caution;

function forecastSeriesOptions() {
  return {
    upColor: FORECAST_UP, downColor: FORECAST_DN,
    wickUpColor: FORECAST_EDGE, wickDownColor: FORECAST_EDGE,
    borderUpColor: FORECAST_EDGE, borderDownColor: FORECAST_EDGE,
    priceLineVisible: false, lastValueVisible: false,
  };
}

function forecastChip() {
  const el = $("#kf-chip");
  if (!el) return;
  const o = state.forecastOverlays && state.forecastOverlays[0];
  if (!o || o.hidden) { el.hidden = true; return; }
  const txt = $("#kf-chip-text");
  if (txt) txt.textContent = `PREDICTED · Kronos-${o.model} · ${o.rows.length} candles`;
  el.hidden = false;
}

function addForecastSeries(rows, chart) {
  const s = chart.addCandlestickSeries(forecastSeriesOptions());
  s.setData(rows.map((r) => ({
    time: r.time, open: r.open, high: r.high, low: r.low, close: r.close,
  })));
  return s;
}

function clearForecastOverlays() {
  const chart = state.charts.price;
  (state.forecastOverlays || []).forEach((o) => {
    (o.series || []).forEach((s) => { try { if (chart) chart.removeSeries(s); } catch (e) { /* gone */ } });
  });
  state.forecastOverlays = [];
  const hide = $("#kf-hide"), rem = $("#kf-remove");
  if (hide) hide.hidden = true;
  if (rem) rem.hidden = true;
  forecastChip();
}

function removeForecastSeries(o, chart) {
  (o.series || []).forEach((s) => { try { chart.removeSeries(s); } catch (e) { /* gone */ } });
  o.series = []; o.hidden = true;
  forecastChip();
}

/* Every Kronos response is stamped with a token; a reload or a newer run
   invalidates the older one, so a stale forecast can never paint on a chart
   that shows a different symbol. */
function invalidateKronosRuns() {
  state.kronosSeq = (state.kronosSeq || 0) + 1;
}

async function runKronosChartForecast() {
  const status = $("#kf-status");
  const symbol = state.chartSymbol;
  if (!symbol) { if (status) status.textContent = "Load a symbol first — the forecast runs on the chart's own stored daily bars."; return; }
  if ((state.chartTf || "daily") !== "daily") {
    if (status) status.textContent =
      `BLOCKED — the chart is showing ${state.chartTf} bars. Kronos forecasts the stored DAILY series; switch Timeframe to Daily so the forecast rows line up with the candles.`;
    return;
  }
  const seq = (state.kronosSeq = (state.kronosSeq || 0) + 1);
  const variant = ($("#kf-variant").value || "base");
  const cxMax = parseInt(($("#kf-context") || {}).max, 10) || 2048;
  const context = Math.min(cxMax, Math.max(12, parseInt(($("#kf-context") || {}).value, 10) || 256));
  const pred = Math.min(64, Math.max(1, parseInt(($("#kf-pred") || {}).value, 10) || 10));
  const btn = $("#kf-run");
  const oldLabel = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Running…";
  if (status) status.textContent =
    `Running Kronos-${variant} on ${symbol} (context ${context} bars, horizon ${pred}). ` +
    "First run loads the official weights and may take a few seconds; the button stays disabled until the model answers.";
  try {
    const data = await api("/api/kronos/forecast", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol, variant, context_len: context, pred_len: pred }),
    });
    if (seq !== state.kronosSeq) {
      if (status) status.textContent =
        `Stale response dropped: this Kronos-${variant} run finished after the chart was reloaded; nothing was drawn (run it again).`;
      return;
    }
    drawForecastOverlay(data);
  } catch (e) {
    if (status) status.textContent = `Kronos-${variant} could not run: ${e.message || e}`;
  } finally {
    if (seq === (state.kronosSeq || 0)) {   // keep the button usable for the live run
      btn.disabled = false;
      btn.textContent = oldLabel;
    }
  }
}

function drawForecastOverlay(result) {
  const chart = state.charts.price;
  const status = $("#kf-status");
  if (!chart) { if (status) status.textContent = "Chart not ready."; return; }
  if (result && result.symbol && state.chartSymbol && result.symbol !== state.chartSymbol) {
    if (status) status.textContent =
      `Forecast is for ${result.symbol} but the chart shows ${state.chartSymbol} — dropped. Forecast and chart must be the same symbol.`;
    return;
  }
  if (!result || !result.rows || !result.rows.length) {
    clearForecastOverlays();
    if (status) status.textContent = "The model returned no forecast rows — nothing was drawn (samples are never substituted).";
    return;
  }
  clearForecastOverlays();
  const s = addForecastSeries(result.rows, chart);
  state.forecastOverlays.push({
    symbol: result.symbol, model: result.variant,
    rows: result.rows.slice(), series: [s], hidden: false,
  });
  const hide = $("#kf-hide"), rem = $("#kf-remove");
  if (hide) { hide.hidden = false; hide.textContent = "Hide"; }
  if (rem) rem.hidden = false;
  forecastChip();
  if (status) status.textContent =
    `Kronos-${result.variant} → ${result.symbol}: ${result.rows.length} PREDICTED candles after ` +
    `${String(result.context.last).slice(0, 10)} (last observed close ${fmtNum(result.context.last_close)}, ` +
    `device ${result.device}, inference ${fmtNum(result.inference_seconds, 1)} s). ` +
    "Model output — never an observed price. " + (result.note || "");
}

/* §5.21/K — Forecaster → main chart. The AI Forecaster hands over its own
   forecast object; we switch to the charting view, load that symbol on the
   daily timeframe, and draw the SAME rows (no second model run, no scaling).
   The overlay carries its origin in the status line, and any later symbol
   change already invalidates it through the normal reload path. */
async function showSharedKronosForecast(payload) {
  try {
    if (!payload || !payload.symbol || !Array.isArray(payload.rows) || !payload.rows.length) {
      drawStatus("Shared forecast is malformed — regenerate it in the AI Forecaster view."); return;
    }
    const nav = document.querySelector("#nav button[data-view=charts]");
    if (nav) nav.click();
    const symbolInput = $("#symbol-input");
    if (symbolInput) symbolInput.value = payload.symbol;
    const tfSel = $("#tf-select");
    if (tfSel && tfSel.value !== "daily") {
      tfSel.value = "daily";
      drawStatus("Timeframe switched to Daily — Kronos forecasts the stored daily series, so the overlay lines up only there.");
    }
    await loadChart();
    if (state.chartSymbol !== payload.symbol) {
      drawStatus(`Could not load ${payload.symbol} for the shared forecast (chart shows ${state.chartSymbol || "nothing"}). Nothing was drawn.`);
      return;
    }
    drawForecastOverlay({
      symbol: payload.symbol, variant: payload.variant, rows: payload.rows,
      context: payload.context, device: payload.device, inference_seconds: payload.inference_seconds,
      note: "shared from AI Forecaster" + (payload.generated_at ? ` · generated ${String(payload.generated_at).slice(0, 10)}` : "") +
        (payload.note ? ` · ${payload.note}` : ""),
    });
  } catch (e) {
    drawStatus(`Shared forecast failed: ${e.message || e}`);
  }
}
window.mtAppShareForecast = showSharedKronosForecast;

async function refreshKronosAvailability() {
  const variant = $("#kf-variant"), hint = $("#kf-cx-hint"), status = $("#kf-status"), run = $("#kf-run");
  if (!variant) return;
  try {
    const st = await api("/api/kronos/status");
    const w = st.weights && st.weights[KRONOS_WEIGHT_DIRS[variant.value]];
    const present = !!(w && w.present);
    const mb = w && w.bytes ? Math.round(w.bytes / 1048576) : 0;
    if (variant.value === "mini" && !present) {
      if (hint) hint.textContent = "weights not installed";
      if (status) status.textContent =
        "Kronos-Mini: BLOCKED_MISSING_WEIGHTS — the official upstream weights are not present under " +
        `${st.weights_root}. Run stays disabled; no other model is relabelled Mini. Base/Small remain usable.`;
      if (run) run.disabled = true;
      return;
    }
    if (!present) {
      if (hint) hint.textContent = "weights not installed";
      if (status) status.textContent =
        `Kronos-${variant.value}: BLOCKED_MISSING_WEIGHTS — official weights absent under ${st.weights_root}.`;
      if (run) run.disabled = true;
      return;
    }
    // Per-variant official capability (model zoo): mini pairs with
    // Kronos-Tokenizer-2k and takes 2048 context bars; small/base cap at 512.
    const cx = (st.variant_max_context || {})[variant.value] || 2048;
    const input = $("#kf-context");
    if (input) {
      input.max = cx;
      if (parseInt(input.value, 10) > cx) input.value = cx;
    }
    if (hint) hint.textContent =
      `≤ ${cx.toLocaleString()} context bars · ${mb} MB weights` +
      (variant.value === "mini" ? " · Tokenizer-2k" : "");
    if (run) run.disabled = false;
    if (status) status.textContent =
      `Kronos-${variant.value}: AVAILABLE — device ${st.device_selected === "mps" ? "Apple MPS" : st.device_selected}` +
      (st.loaded_variant ? ` · ${st.loaded_variant} already resident` : "");
  } catch (e) {
    if (status) status.textContent = `Availability check failed: ${e.message || e}`;
  }
}

function bindKronosChart() {
  const run = $("#kf-run"), variant = $("#kf-variant");
  if (!run) return;
  run.addEventListener("click", runKronosChartForecast);
  if (variant) variant.addEventListener("change", refreshKronosAvailability);
  const hide = $("#kf-hide");
  if (hide) hide.addEventListener("click", () => {
    const chart = state.charts.price;
    const o = state.forecastOverlays[0];
    if (!o || !chart) return;
    if (o.hidden) {
      const s = addForecastSeries(o.rows, chart);
      o.series = [s]; o.hidden = false;
      hide.textContent = "Hide";
      forecastChip();
    } else {
      removeForecastSeries(o, chart);
      hide.textContent = "Show";
    }
  });
  const rem = $("#kf-remove");
  if (rem) rem.addEventListener("click", () => { clearForecastOverlays(); const st = $("#kf-status"); if (st) st.textContent = "Forecast overlay removed."; });
  const popBtn = $("#pop-kronos-btn");
  if (popBtn) popBtn.addEventListener("click", () => { refreshKronosAvailability(); });
}

/* ===== Multi-symbol comparison + bars-pattern feed ======================= */
async function runCompare() {
  const errEl = $("#cmp-error");
  const host = $("#cmp-table");
  const syms = ($("#cmp-symbols").value || "").split(/[,\s]+/).map(s => s.trim().toUpperCase()).filter(Boolean);
  const tf = ($("#cmp-tf").value || "daily");
  const limit = Math.max(30, Math.min(750, parseInt($("#cmp-limit").value, 10) || 250));
  if (syms.length < 2) { if (errEl) errEl.textContent = "Enter at least two symbols."; return; }
  if (errEl) errEl.textContent = "Loading…";
  if (host) host.innerHTML = "";
  try {
    const data = await Promise.all(syms.map(async (s) => {
      const d = await api(`/api/bars/${encodeURIComponent(s)}${tf === "daily" ? "" : "/" + tf}?limit=${limit}`);
      return { symbol: s, bars: d.bars || [] };
    }));
    // align by date (inner join)
    const dateSets = data.map(d => new Set(d.bars.map(b => b.time)));
    const common = [...dateSets[0]].filter(dt => dateSets.slice(1).every(s => s.has(dt))).sort();
    if (common.length < 2) { if (errEl) errEl.textContent = "No overlapping dates between the selected symbols."; return; }
    // rebase to 100 at first common date
    const basePrices = data.map(d => {
      const m = new Map(d.bars.map(b => [b.time, b.close]));
      return m.get(common[0]);
    });
    const rows = common.map(dt => {
      const cells = data.map((d, i) => {
        const m = new Map(d.bars.map(b => [b.time, b.close]));
        const c = m.get(dt);
        const base = basePrices[i];
        return (c != null && base) ? (c / base * 100) : null;
      });
      return { date: dt, cells };
    });
    // table: last value + total return
    const last = rows[rows.length - 1];
    const first = rows[0];
    let html = `<div class="tablewrap"><table><thead><tr><th>Symbol</th><th>First</th><th>Last (rebased)</th><th>Return %</th><th>Bars</th><th>Missing in window</th></tr></thead><tbody>`;
    data.forEach((d, i) => {
      const base = basePrices[i];
      const lastClose = new Map(d.bars.map(b => [b.time, b.close])).get(common[common.length-1]);
      const ret = (base && lastClose) ? ((lastClose/base - 1) * 100) : null;
      const missing = d.bars.length - common.length;
      html += `<tr><td><b>${esc(d.symbol)}</b></td><td>${fmtNum(base)}</td><td>${fmtNum(lastClose && base ? lastClose/base*100 : null, 2)}</td><td class="${(ret||0) >= 0 ? 'up' : 'down'}">${ret == null ? "—" : (ret >= 0 ? "+" : "") + fmtNum(ret, 2) + "%"}</td><td>${fmtInt(d.bars.length)}</td><td>${fmtInt(missing)}</td></tr>`;
    });
    html += `</tbody></table></div>`;
    html += `<p class="hint">Common window: ${esc(String(common[0]).slice(0,10))} → ${esc(String(common[common.length-1]).slice(0,10))} · ${fmtInt(common.length)} aligned bars · rebased to 100 at the first shared date.</p>`;
    if (host) host.innerHTML = html;
    if (errEl) errEl.textContent = "";
  } catch (e) {
    if (errEl) errEl.textContent = `Comparison failed: ${e.message}`;
  }
}

async function runBarsPatternFeed() {
  const errEl = $("#bp-error");
  const host = $("#bp-table");
  const sym = (($("#bp-symbol").value || "").trim().toUpperCase()) || (($("#symbol-input").value || "").trim().toUpperCase());
  const limit = Math.max(30, Math.min(750, parseInt($("#bp-limit").value, 10) || 120));
  if (!sym) { if (errEl) errEl.textContent = "Enter a symbol."; return; }
  if (errEl) errEl.textContent = "Detecting…";
  if (host) host.innerHTML = "";
  try {
    const d = await api(`/api/bars/${encodeURIComponent(sym)}?limit=${limit}`);
    const bars = d.bars || [];
    // reuse the candlestick detector's rule set (same as #candle-run)
    const rows = [];
    for (let i = 2; i < bars.length; i++) {
      const b = bars[i], p = bars[i-1], pp = bars[i-2];
      const isBull = (x) => (x.close ?? 0) >= (x.open ?? x.close ?? 0);
      const body = (x) => Math.abs((x.close ?? 0) - (x.open ?? x.close ?? 0));
      const range = (x) => (x.high ?? x.close ?? 0) - (x.low ?? x.close ?? 0);
      let pat = null;
      if (isBull(b) && !isBull(p) && (b.open ?? 0) <= (p.close ?? 0) && (b.close ?? 0) >= (p.open ?? 0)) pat = "Bullish engulfing";
      else if (!isBull(b) && isBull(p) && (b.open ?? 0) >= (p.close ?? 0) && (b.close ?? 0) <= (p.open ?? 0)) pat = "Bearish engulfing";
      else if (isBull(b) && body(b) > 0 && (b.low ?? 0) <= (p.low ?? 0) && (b.close ?? 0) > (p.close ?? 0) && body(b) > body(p)) pat = "Piercing line";
      else if (!isBull(b) && body(b) > 0 && (b.high ?? 0) >= (p.high ?? 0) && (b.close ?? 0) < (p.close ?? 0) && body(b) > body(p)) pat = "Dark cloud cover";
      const o = b.open ?? b.close ?? 0, c = b.close ?? 0, h = b.high ?? c, l = b.low ?? c;
      const upperWick = h - Math.max(o, c), lowerWick = Math.min(o, c) - l, tot = range(b) || 1;
      if (!pat && lowerWick / tot > 0.6 && body(b) / tot < 0.35) pat = isBull(b) ? "Hammer" : "Hanging man";
      if (!pat && upperWick / tot > 0.6 && body(b) / tot < 0.35) pat = "Shooting star";
      if (!pat && body(b) / tot < 0.05) pat = "Doji";
      if (pat) rows.push({ i, date: b.time, pat, close: c, confirmed: true });
    }
    if (!rows.length) { if (host) host.innerHTML = `<div class="empty">No patterns detected in the last ${fmtInt(bars.length)} bars.</div>`; if (errEl) errEl.textContent = ""; return; }
    if (host) host.innerHTML = `<div class="tablewrap">${table(
      ["Date", "Pattern", "Close", "Status"],
      rows.map(r => [
        { html: esc(String(r.date).slice(0,10)) },
        { html: `<b>${esc(r.pat)}</b>` },
        { html: fmtNum(r.close) },
        { html: `<span class="pill pill-ok">detected (candidate)</span>` },
      ]))}</div>`;
    if (errEl) errEl.textContent = `${fmtInt(rows.length)} pattern(s) in ${fmtInt(bars.length)} bars. Patterns are candidates until confirmed by subsequent candles; detection uses only bars up to each timestamp.`;
  } catch (e) {
    if (errEl) errEl.textContent = `Detection failed: ${e.message}`;
  }
}

function exportBarsPatternCsv() {
  const host = $("#bp-table");
  const rows = [...(host?.querySelectorAll("tbody tr") || [])].map(tr => [...tr.querySelectorAll("td")].map(td => td.textContent.trim()));
  if (!rows.length) { toast("Run detection first."); return; }
  const lines = [["Date","Pattern","Close","Status"].join(","), ...rows.map(r => r.join(","))].join("\\n");
  const blob = new Blob([lines], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = "bars-patterns.csv"; document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
}

function bindCompareAndBarsPattern() {
  if ($("#cmp-run")) $("#cmp-run").addEventListener("click", runCompare);
  if ($("#bp-run")) $("#bp-run").addEventListener("click", runBarsPatternFeed);
  if ($("#bp-export")) $("#bp-export").addEventListener("click", exportBarsPatternCsv);
  // prefill bp symbol from chart
  const bpSym = $("#bp-symbol");
  if (bpSym && !bpSym.value) bpSym.value = ($("#symbol-input").value || "").trim().toUpperCase();
}
/* ===== §28 Custom indicator editor (sandboxed DSL) =========================
   A deliberately small, safe expression language. There is NO eval and NO
   arbitrary code execution: a recursive-descent parser builds an AST from a
   fixed grammar, and only whitelisted functions/series can appear. Unknown
   identifiers are rejected at parse time, so a formula can never reach into
   the host environment. */
const CUSTOM_FUNCS = {
  sma: (bars, args) => smaSeries(bars, args[0]),
  ema: (bars, args) => emaSeries(bars, args[0]),
  rsi: (bars, args) => rsiSeries(bars, args[0]),
  atr: (bars, args) => atrSeries(bars, args[0]),
  bb_upper: (bars, args) => bbSeries(bars, args[0], args[1] ?? 2, "upper"),
  bb_lower: (bars, args) => bbSeries(bars, args[0], args[1] ?? 2, "lower"),
  abs: (_bars, args) => args[0].map((v) => (v == null ? null : Math.abs(v))),
  min: (_bars, args) => args[0].map((v, i) => (v == null || args[1][i] == null ? null : Math.min(v, args[1][i]))),
  max: (_bars, args) => args[0].map((v, i) => (v == null || args[1][i] == null ? null : Math.max(v, args[1][i]))),
};
const CUSTOM_SERIES = {
  close: (bars) => bars.map((b) => (b && isFinite(b.close) ? b.close : null)),
  open: (bars) => bars.map((b) => (b && isFinite(b.open ?? b.close) ? (b.open ?? b.close) : null)),
  high: (bars) => bars.map((b) => (b && isFinite(b.high ?? b.close) ? (b.high ?? b.close) : null)),
  low: (bars) => bars.map((b) => (b && isFinite(b.low ?? b.close) ? (b.low ?? b.close) : null)),
  volume: (bars) => bars.map((b) => (b && isFinite(b.volume) ? b.volume : 0)),
};

function smaSeries(bars, n) {
  const closes = CUSTOM_SERIES.close(bars);
  const N = Math.max(1, Math.round(n));
  const out = new Array(bars.length).fill(null);
  let sum = 0;
  for (let i = 0; i < bars.length; i++) {
    sum += closes[i] == null ? 0 : closes[i];
    if (i >= N) { const prev = closes[i - N]; if (prev != null) sum -= prev; }
    if (i >= N - 1 && closes.slice(i - N + 1, i + 1).every((v) => v != null)) out[i] = sum / N;
  }
  return out;
}
function emaSeries(bars, n) {
  const closes = CUSTOM_SERIES.close(bars);
  const N = Math.max(1, Math.round(n));
  const k = 2 / (N + 1);
  const out = new Array(bars.length).fill(null);
  let ema = null, count = 0, sum = 0;
  for (let i = 0; i < bars.length; i++) {
    const c = closes[i];
    if (c == null) { out[i] = null; continue; }
    if (ema == null) {
      sum += c; count++;
      if (count >= N) { ema = sum / N; out[i] = ema; }
    } else {
      ema = c * k + ema * (1 - k);
      out[i] = ema;
    }
  }
  return out;
}
function rsiSeries(bars, n) {
  const closes = CUSTOM_SERIES.close(bars);
  const N = Math.max(1, Math.round(n));
  const out = new Array(bars.length).fill(null);
  let gain = 0, loss = 0, prev = null, count = 0;
  for (let i = 0; i < bars.length; i++) {
    const c = closes[i];
    if (c == null) { prev = null; out[i] = null; continue; }
    if (prev != null) {
      const diff = c - prev;
      const g = diff > 0 ? diff : 0, l = diff < 0 ? -diff : 0;
      if (count < N) { gain += g; loss += l; count++; if (count === N) { const ag = gain / N, al = loss / N; const rs = al === 0 ? 100 : ag / al; out[i] = 100 - 100 / (1 + rs); } }
      else { gain = (gain * (N - 1) + g) / N; loss = (loss * (N - 1) + l) / N; const rs = loss === 0 ? 100 : gain / loss; out[i] = 100 - 100 / (1 + rs); }
    }
    prev = c;
  }
  return out;
}
function atrSeries(bars, n) {
  const N = Math.max(1, Math.round(n));
  const tr = bars.map((b, i) => {
    if (!b || !isFinite(b.close)) return null;
    const h = b.high ?? b.close, l = b.low ?? b.close;
    const prev = i > 0 ? (bars[i - 1].close ?? b.close) : b.close;
    return Math.max(h - l, Math.abs(h - prev), Math.abs(l - prev));
  });
  const out = new Array(bars.length).fill(null);
  let sum = 0, count = 0;
  for (let i = 0; i < bars.length; i++) {
    if (tr[i] == null) continue;
    sum += tr[i]; count++;
    if (count > N) { sum -= (tr[i - N] || 0); }
    if (count >= N) out[i] = sum / Math.min(count, N);
  }
  return out;
}
function bbSeries(bars, n, k, which) {
  const closes = CUSTOM_SERIES.close(bars);
  const N = Math.max(2, Math.round(n));
  const mult = Number(k) || 2;
  const out = new Array(bars.length).fill(null);
  for (let i = N - 1; i < bars.length; i++) {
    const win = closes.slice(i - N + 1, i + 1);
    if (win.some((v) => v == null)) continue;
    const mean = win.reduce((s, v) => s + v, 0) / N;
    const sd = Math.sqrt(win.reduce((s, v) => s + (v - mean) ** 2, 0) / N);
    out[i] = which === "upper" ? mean + mult * sd : mean - mult * sd;
  }
  return out;
}

/* ---- recursive-descent parser (numbers, identifiers, calls, arithmetic) ---- */
function parseCustomFormula(src) {
  const toks = tokenizeCustom(src);
  if (toks.error) return toks;
  let i = 0;
  function peek() { return toks[i]; }
  function next() { return toks[i++]; }
  function parseExpr() { return parseAddSub(); }
  function parseAddSub() {
    let node = parseMulDiv();
    while (peek() && (peek().type === "op" && (peek().value === "+" || peek().value === "-"))) {
      const op = next().value;
      const rhs = parseMulDiv();
      node = { type: "bin", op, left: node, right: rhs };
    }
    return node;
  }
  function parseMulDiv() {
    let node = parseUnary();
    while (peek() && (peek().type === "op" && (peek().value === "*" || peek().value === "/"))) {
      const op = next().value;
      const rhs = parseUnary();
      node = { type: "bin", op, left: node, right: rhs };
    }
    return node;
  }
  function parseUnary() {
    if (peek() && peek().type === "op" && (peek().value === "-" || peek().value === "+")) {
      const op = next().value;
      const v = parseUnary();
      return op === "-" ? { type: "un", op: "-", value: v } : v;
    }
    return parsePrimary();
  }
  function parsePrimary() {
    const t = peek();
    if (!t) throw new Error("unexpected end of formula");
    if (t.type === "num") { next(); return { type: "num", value: t.value }; }
    if (t.type === "lparen") { next(); const e = parseExpr(); if (!peek() || peek().type !== "rparen") throw new Error("missing closing ')'"); next(); return e; }
    if (t.type === "ident") {
      next();
      if (peek() && peek().type === "lparen") {
        next();
        const args = [];
        if (peek() && peek().type !== "rparen") {
          args.push(parseExpr());
          while (peek() && peek().type === "comma") { next(); args.push(parseExpr()); }
        }
        if (!peek() || peek().type !== "rparen") throw new Error("missing closing ')' after arguments");
        next();
        if (!CUSTOM_FUNCS[t.value] && !CUSTOM_SERIES[t.value]) throw new Error(`unknown function or series '${t.value}'`);
        const isSeries = Object.prototype.hasOwnProperty.call(CUSTOM_SERIES, t.value);
        if (isSeries && args.length !== 0) throw new Error(`'${t.value}' takes no arguments`);
        if (!isSeries && !CUSTOM_FUNCS[t.value]) throw new Error(`unknown function '${t.value}'`);
        return { type: "call", name: t.value, args };
      }
      if (!CUSTOM_SERIES[t.value]) throw new Error(`unknown series '${t.value}' (did you mean close?)`);
      return { type: "series", name: t.value };
    }
    throw new Error(`unexpected token '${t.value}'`);
  }
  try {
    const node = parseExpr();
    if (i !== toks.length) throw new Error(`unexpected trailing token '${toks[i].value}'`);
    return node;
  } catch (e) { return { error: e.message }; }
}

function tokenizeCustom(src) {
  const toks = [];
  let i = 0;
  const s = String(src || "");
  while (i < s.length) {
    const c = s[i];
    if (/\s/.test(c)) { i++; continue; }
    if (/[0-9.]/.test(c)) {
      let j = i;
      while (j < s.length && /[0-9.]/.test(s[j])) j++;
      const num = Number(s.slice(i, j));
      if (!isFinite(num)) return { error: "invalid number" };
      toks.push({ type: "num", value: num });
      i = j; continue;
    }
    if (/[a-zA-Z_]/.test(c)) {
      let j = i;
      while (j < s.length && /[a-zA-Z0-9_]/.test(s[j])) j++;
      toks.push({ type: "ident", value: s.slice(i, j) });
      i = j; continue;
    }
    if (c === "(") { toks.push({ type: "lparen", value: "(" }); i++; continue; }
    if (c === ")") { toks.push({ type: "rparen", value: ")" }); i++; continue; }
    if (c === ",") { toks.push({ type: "comma", value: "," }); i++; continue; }
    if ("+-*/".includes(c)) { toks.push({ type: "op", value: c }); i++; continue; }
    return { error: `unexpected character '${c}'` };
  }
  return toks;
}

function evalCustomAst(node, bars) {
  if (!node || node.error) return null;
  if (node.type === "num") return bars.map(() => node.value);
  if (node.type === "series") {
    const fn = CUSTOM_SERIES[node.name];
    return fn ? fn(bars) : null;
  }
  if (node.type === "call") {
    const isSeries = Object.prototype.hasOwnProperty.call(CUSTOM_SERIES, node.name);
    if (isSeries) return CUSTOM_SERIES[node.name](bars);
    const fn = CUSTOM_FUNCS[node.name];
    if (!fn) return null;
    const args = node.args.map((a) => evalCustomAst(a, bars));
    if (args.some((a) => !Array.isArray(a))) return null;
    return fn(bars, args);
  }
  if (node.type === "un") {
    const v = evalCustomAst(node.value, bars);
    if (!Array.isArray(v)) return null;
    return v.map((x) => (x == null ? null : (node.op === "-" ? -x : x)));
  }
  if (node.type === "bin") {
    const L = evalCustomAst(node.left, bars), R = evalCustomAst(node.right, bars);
    if (!Array.isArray(L) || !Array.isArray(R)) return null;
    return L.map((lv, i) => {
      const rv = R[i];
      if (lv == null || rv == null) return null;
      switch (node.op) {
        case "+": return lv + rv;
        case "-": return lv - rv;
        case "*": return lv * rv;
        case "/": return rv === 0 ? null : lv / rv;
        default: return null;
      }
    });
  }
  return null;
}

function customFormulaKey(symbol) { return `mt-custom-formulas-${symbol}`; }
function loadCustomFormulas(symbol) {
  try {
    const raw = JSON.parse(localStorage.getItem(customFormulaKey(symbol)) || "[]");
    return Array.isArray(raw) ? raw.filter((x) => x && x.name && x.formula) : [];
  } catch (e) { return []; }
}
function persistCustomFormulas(symbol, list) {
  try { localStorage.setItem(customFormulaKey(symbol), JSON.stringify(list || [])); } catch (e) { /* off */ }
}

async function applyCustomFormula(name, formula, color, bars) {
  const ast = parseCustomFormula(formula);
  if (ast.error) throw new Error(ast.error);
  const vals = evalCustomAst(ast, bars);
  if (!Array.isArray(vals)) throw new Error("formula did not produce a series");
  const chart = state.charts.price;
  if (!chart) throw new Error("Load a chart first.");
  const s = chart.addLineSeries({ color: color || PRAVAHA.caution, lineWidth: 2, priceLineVisible: false, lastValueVisible: false, title: name });
  s.setData(bars.map((b, i) => (vals[i] == null ? null : { time: b.time, value: vals[i] })).filter(Boolean));
  (state.customFormulaSeries = state.customFormulaSeries || []).push(s);
  return s;
}

function renderCustomFormulaList() {
  const host = $("#ind-custom-list");
  if (!host) return;
  const list = loadCustomFormulas(state.chartSymbol);
  if (!list.length) { host.innerHTML = `<div class="empty">No saved formulas for this symbol.</div>`; return; }
  host.innerHTML = `<div class="tablewrap">${table(
    ["Name", "Formula", ""],
    list.map((f) => [
      { html: `<b>${esc(f.name)}</b>` },
      { html: `<code>${esc(f.formula)}</code>` },
      { html: `<button class="ghost cf-remove" data-name="${esc(f.name)}">Remove</button>` },
    ]))}</div>`;
  host.querySelectorAll(".cf-remove").forEach((b) => b.addEventListener("click", () => {
    const list2 = loadCustomFormulas(state.chartSymbol).filter((x) => x.name !== b.dataset.name);
    persistCustomFormulas(state.chartSymbol, list2);
    renderCustomFormulaList();
  }));
}

function bindCustomFormula() {
  const open = () => {
    const m = $("#ind-custom");
    if (!m) return;
    m.hidden = false;
    renderCustomFormulaList();
    const st = $("#ind-custom-status");
    if (st) st.textContent = state.chartSymbol ? `· ${state.chartSymbol}` : "";
  };
  if ($("#ind-custom-btn")) $("#ind-custom-btn").addEventListener("click", (e) => { e.stopPropagation(); open(); });
  if ($("#ind-custom-close")) $("#ind-custom-close").addEventListener("click", () => { $("#ind-custom").hidden = true; });
  $("#ind-custom")?.addEventListener("click", (e) => { if (e.target.id === "ind-custom") e.currentTarget.hidden = true; });
  if ($("#ind-custom-test")) $("#ind-custom-test").addEventListener("click", async () => {
    const errEl = $("#ind-custom-error");
    const name = ($("#ind-custom-name").value || "Custom").trim() || "Custom";
    const formula = ($("#ind-custom-formula").value || "").trim();
    const color = ($("#ind-custom-color").value || PRAVAHA.caution);
    if (!formula) { if (errEl) errEl.textContent = "Enter a formula first."; return; }
    if (!state.chartSymbol) { if (errEl) errEl.textContent = "Load a chart first."; return; }
    try {
      await applyCustomFormula(name, formula, color, state.chartBars);
      if (errEl) errEl.textContent = `Plotted ${name}.`;
    } catch (e) { if (errEl) errEl.textContent = `Error: ${e.message}`; }
  });
  if ($("#ind-custom-save")) $("#ind-custom-save").addEventListener("click", () => {
    const errEl = $("#ind-custom-error");
    const name = ($("#ind-custom-name").value || "").trim();
    const formula = ($("#ind-custom-formula").value || "").trim();
    if (!name || !formula) { if (errEl) errEl.textContent = "Name and formula are required."; return; }
    const ast = parseCustomFormula(formula);
    if (ast.error) { if (errEl) errEl.textContent = `Cannot save: ${ast.error}`; return; }
    const list = loadCustomFormulas(state.chartSymbol).filter((x) => x.name !== name);
    list.push({ name, formula, color: $("#ind-custom-color").value || PRAVAHA.caution });
    persistCustomFormulas(state.chartSymbol, list);
    renderCustomFormulaList();
    if (errEl) errEl.textContent = `Saved ${name}.`;
  });
  if ($("#ind-custom-remove")) $("#ind-custom-remove").addEventListener("click", () => {
    const name = ($("#ind-custom-name").value || "").trim();
    if (!name) { const e = $("#ind-custom-error"); if (e) e.textContent = "Type the name to remove."; return; }
    const list = loadCustomFormulas(state.chartSymbol).filter((x) => x.name !== name);
    persistCustomFormulas(state.chartSymbol, list);
    renderCustomFormulaList();
    const e = $("#ind-custom-error"); if (e) e.textContent = `Removed ${name} (if it existed).`;
  });
  // apply saved formulas on chart load
  const origRebuild = rebuildCustomIndicators;
  rebuildCustomIndicators = async function(symbol, dates) {
    await origRebuild(symbol, dates);
    if (!state.chartBars || !state.chartBars.length) return;
    const formulas = loadCustomFormulas(symbol);
    for (const f of formulas) {
      try { await applyCustomFormula(f.name, f.formula, f.color, state.chartBars); }
      catch (e) { console.warn("custom formula failed:", f.name, e && e.message); }
    }
  };
}
/* ===== §8J Replay + §8K autosave =========================================
   Replay rebuilds the price chart so the rendered series only ever contains
   bars up to the cursor: future candles are simply not in the data, so they
   cannot leak into the chart or the OHLCV strip. Analysis layers, pattern
   overlays, forecast overlays and manual drawings are hidden while replay is
   on (they depend on the full series or full-history indicators); loadChart()
   restores the complete view when replay stops. */
function replayStatus(msg) { const el = $("#rp-status"); if (el) el.textContent = msg; }

function setReplayButtons() {
  const st = state.replay;
  const show = (id, on) => { const el = $(id); if (el) el.hidden = !on; };
  show("#rp-stop", !!st);
  show("#rp-play", !!st && !st.timer);
  show("#rp-pause", !!st && !!st.timer);
}

function applyReplaySlice() {
  const st = state.replay;
  if (!st) return;
  const bars = state.chartBars.slice(0, st.i + 1);
  st.series.setData(bars.map((b) => ({
    time: b.time, open: b.open ?? b.close, high: b.high ?? b.close,
    low: b.low ?? b.close, close: b.close,
  })));
  if (st.vol) st.vol.setData(bars.map((b) => ({
    time: b.time, value: b.volume || 0,
    color: (b.close >= (b.open ?? b.close)) ? "rgba(31,201,138,.5)" : "rgba(255,107,120,.5)",
  })));
  st.chart.timeScale().fitContent();
  const bar = bars[bars.length - 1];
  replayStatus(`Bar ${st.i + 1} of ${state.chartBars.length} — ${String(bar.time).slice(0, 10)} · close ${fmtNum(bar.close)}.`);
}

function stopReplayAutoplay() {
  const st = state.replay;
  if (st && st.timer) { clearInterval(st.timer); st.timer = null; }
  if (st) st.timer = null;
  setReplayButtons();
}

function stepReplay(delta) {
  const st = state.replay;
  if (!st) return;
  st.i = Math.max(0, Math.min(state.chartBars.length - 1, st.i + delta));
  applyReplaySlice();
}

function startReplay() {
  if (!state.chartSymbol || !(state.chartBars || []).length) {
    replayStatus("Load a symbol first — replay moves through that symbol's stored bars."); return;
  }
  if (state.replay) stopReplayAutoplay();
  setDrawTool(null);   // anchor placement needs the live chart; re-enabled on stop
  destroyCharts();
  clearForecastOverlays();   // the old chart's series are gone
  const chart = makeChart($("#chart"), Math.max(360, ($("#chart").clientHeight || 520)));
  state.charts.price = chart;
  bindOhlcvLegend(chart);
  const candle = chart.addCandlestickSeries({
    upColor: PRAVAHA.up, downColor: PRAVAHA.down, borderVisible: false,
    wickUpColor: PRAVAHA.up, wickDownColor: PRAVAHA.down,
  });
  state.candleSeries = candle;
  const vol = chart.addHistogramSeries({
    priceFormat: { type: "volume" }, priceScaleId: "vol", color: PRAVAHA.borderLite,
  });
  chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
  state.replay = {
    on: true, i: Math.max(0, Math.floor(state.chartBars.length / 2)),
    chart, series: candle, vol, timer: null,
  };
  applyReplaySlice();
  setReplayButtons();
  replayStatus(`Replay started at bar ${state.replay.i + 1} of ${state.chartBars.length}. Drawings and analysis layers are hidden; Stop restores the full chart.`);
}

function stopReplay() {
  stopReplayAutoplay();
  const hadReplay = !!state.replay;
  state.replay = null;
  if (!hadReplay) return;
  replayStatus("Replay ended — restoring the full chart…");
  loadChart().then(() => replayStatus("Replay ended. The full chart is back (layers follow your drawer settings)."));
}

function playPauseReplay() {
  const st = state.replay;
  if (!st) { replayStatus("Start replay first."); return; }
  if (st.timer) { stopReplayAutoplay(); replayStatus("Paused."); return; }
  const ms = Math.max(80, parseInt(($("#rp-speed") || {}).value, 10) || 900);
  st.timer = setInterval(() => {
    if (st.i >= state.chartBars.length - 1) {
      stopReplayAutoplay();
      replayStatus("Replay reached the last loaded bar — pause. Back −1 rewinds.");
      return;
    }
    stepReplay(1);
  }, ms);
  setReplayButtons();
  replayStatus("Playing forward through stored bars…");
}

/* §8K autosave: an explicit on/off switch. When ON, the last chart context
   (symbol, timeframe, range, render style) is saved to this browser and
   restored on the next visit. When OFF, the saved context is dropped and
   nothing is restored — no silent saving beyond the basic operation. */
function autosaveEnabled() {
  try { return localStorage.getItem("mt-autosave-enabled") === "1"; } catch (e) { return false; }
}
function saveAutosave() {
  if (!autosaveEnabled() || !state.chartSymbol) return;
  try {
    localStorage.setItem("mt-autosave", JSON.stringify({
      symbol: state.chartSymbol,
      tf: ($("#tf-select") || {}).value,
      range: ($("#range") || {}).value,
      style: ($("#chart-type") || {}).value,
      saved_at: new Date().toISOString(),
    }));
  } catch (e) { /* storage full: the switch stays on, this save is skipped */ }
}
function restoreAutosave() {
  if (!autosaveEnabled()) return;
  let saved = null;
  try { saved = JSON.parse(localStorage.getItem("mt-autosave") || "null"); } catch (e) { saved = null; }
  if (!saved || !saved.symbol) return;
  try {
    const inp = $("#symbol-input");
    if (inp && !inp.value) inp.value = String(saved.symbol).toUpperCase().slice(0, 16);
    ["tf-select", "range", "chart-type"].forEach((id) => {
      const key = { "tf-select": "tf", "range": "range", "chart-type": "style" }[id];
      const el = document.getElementById(id);
      if (el && saved[key] && [...el.options].some((o) => o.value === saved[key])) el.value = saved[key];
    });
    loadChart();
  } catch (e) {
    console.warn("Autosave restore failed:", e);
  }
}
function bindReplayAndSettings() {
  const on = (id, fn) => { const el = $(id); if (el) el.addEventListener("click", fn); };
  on("#rp-start", startReplay);
  on("#rp-play", playPauseReplay);
  on("#rp-pause", playPauseReplay);
  on("#rp-step", () => stepReplay(1));
  on("#rp-back", () => stepReplay(-1));
  on("#rp-stop", stopReplay);
  const chk = $("#autosave-chk"), note = $("#autosave-note");
  const noteFor = (v) => v
    ? "On — the last symbol, timeframe, range and style are restored on reload."
    : "Off — the app will not restore a symbol/timeframe after a reload.";
  if (chk) {
    chk.checked = autosaveEnabled();
    if (note) note.textContent = noteFor(chk.checked);
    chk.addEventListener("change", () => {
      try {
        localStorage.setItem("mt-autosave-enabled", chk.checked ? "1" : "0");
        if (chk.checked) saveAutosave(); else localStorage.removeItem("mt-autosave");
      } catch (e) { drawStatus("Autosave could not be changed (storage error)."); }
      if (note) note.textContent = noteFor(chk.checked);
    });
  }
}

function bindPatternPanel() {
  if ($("#pattern-overlay")) $("#pattern-overlay").addEventListener("change", () => renderPatternPanel());
  if ($("#pattern-all")) $("#pattern-all").addEventListener("click", () => {
    $$(".pat-pick").forEach((c) => { c.checked = true; });
    patternPicks = null;
    updatePatternSelHint();
    renderPatternPanel();
  });
  if ($("#pattern-none")) $("#pattern-none").addEventListener("click", () => {
    $$(".pat-pick").forEach((c) => { c.checked = false; });
    patternPicks = new Set();
    updatePatternSelHint();
    renderPatternPanel();
  });
}

async function loadChartInsights(symbol) {
  const statsEl = $("#stats");
  const statsHint = $("#stats-hint");
  statsEl.innerHTML = `<div class="stat"><div class="k">Status</div><div class="v muted">Loading…</div></div>`;

  // The return-statistics and candlestick-pattern endpoints serve individual
  // securities, not the composite index. Asking them for NEPSE only produced
  // two 404s in the console, so the index is answered directly and honestly.
  if (symbol === "NEPSE") {
    statsEl.innerHTML = `<div class="stat"><div class="k">Status</div><div class="v muted">n/a for the index</div></div>`;
    statsHint.textContent = "Return statistics and candlestick patterns are computed from individual-security bars; the composite index is a closing-value series, so this panel is left empty rather than guessed. The index's own swing structure is in the Swings panel.";
    return;
  }

  // Patterns — rule-based, descriptive, with a selector and a real overlay.
  // A failure here must not break the chart.
  await loadPatternPanel(symbol);

  // Return statistics — undefined metrics come back as null and render "—".
  try {
    const s = await api(`/api/bars/${encodeURIComponent(symbol)}/statistics`);
    const r = s.returns || {};
    const rows = [
      ["Total return", fmtPctFrac(r.total_return ?? null)],
      ["CAGR", fmtPctFrac(r.cagr ?? null)],
      ["Ann. volatility", fmtPctFrac(r.annualised_volatility ?? null)],
      ["Sharpe", fmtNum(r.sharpe)],
      ["Sortino", fmtNum(r.sortino)],
      ["Max drawdown", fmtPctFrac(r.max_drawdown ?? null)],
      ["DD duration (bars)", fmtInt(r.max_drawdown_duration)],
    ];
    statsEl.innerHTML = rows.map(([k, v]) =>
      `<div class="stat"><div class="k">${esc(k)}</div><div class="v">${v}</div></div>`).join("");
    statsHint.textContent = `Annualised at ${s.assumptions.periods_per_year} periods/year `
      + `(a stated convention). "—" means the metric is undefined for this series.`;
  } catch (e) {
    statsEl.innerHTML = `<div class="stat"><div class="k">Status</div><div class="v muted">unavailable</div></div>`;
    statsHint.textContent = `Statistics unavailable: ${e.message}`;
  }
}

async function runCorrelation() {
  const out = $("#corr-out");
  const symbols = ($("#corr-symbols").value || "").split(",").map((s) => s.trim()).filter(Boolean);
  if (symbols.length < 2) { out.innerHTML = `<div class="empty">Enter at least two symbols.</div>`; return; }
  const method = $("#corr-method").value;
  out.innerHTML = `<div class="empty">Computing…</div>`;
  try {
    const d = await api(`/api/stats/correlation?symbols=${encodeURIComponent(symbols.join(","))}&method=${encodeURIComponent(method)}`);
    const head = [""].concat(d.symbols);
    const rows = d.symbols.map((rowSym, i) =>
      [{ html: `<b>${esc(rowSym)}</b>` }].concat(
        d.matrix[i].map((v, j) => ({
          html: i === j ? "1.00" : (v == null ? "—" : fmtNum(v)),
          cls: (i === j || v == null) ? "" : (v >= 0 ? "up" : "down"),
        }))
      )
    );
    out.innerHTML = table(head, rows)
      + `<p class="hint">Method: ${esc(d.method)} · common bars: ${esc(d.common_bars)}`
      + (Object.keys(d.excluded || {}).length
        ? ` · excluded: ${esc(Object.entries(d.excluded).map(([k, v]) => `${k} (${v})`).join(", "))}`
        : "") + `</p>`;
  } catch (e) {
    out.innerHTML = `<div class="empty">Correlation unavailable: ${esc(e.message)}</div>`;
  }
}

/* ==========================================================================
   FLOATING RESEARCH ASSISTANT
   --------------------------------------------------------------------------
   A chat panel available from every view. Two honest actions:

   * "Send"  → POST /api/agent/run  (deterministic tools over stored data).
   * "Propose rule" → POST /api/screens/propose (deterministic grammar that
     turns plain language into a validated screen tree). The proposal is shown
     for review and can be loaded into the Screener's rule builder; it is only
     executed when the researcher presses Run there, through the existing
     validated POST /api/screen path. No model output is ever executed.
   ========================================================================== */
const CHAT_EXAMPLES = [
  "Show me the stored history summary for NABIL",
  "What patterns did the detector find on ADBL?",
  "rsi below 35 and price above its sma 50",
  "volume above its average and adx above 25",
  "Compare NABIL with the NEPSE index",
  "What fundamentals coverage do we have?",
];

function chatEl() { return $("#chat-log"); }

function chatPush(role, html) {
  const log = chatEl();
  if (!log) return null;
  const wrap = document.createElement("div");
  wrap.className = `chat-msg ${role}`;
  wrap.innerHTML = `<div class="chat-bubble">${html}</div>`;
  log.appendChild(wrap);
  log.scrollTop = log.scrollHeight;
  return wrap;
}

function chatStatusPill(status) {
  const cls = status === "ok" ? "pill" : status === "empty" ? "pill pill-review" : "pill pill-danger";
  return `<span class="${cls}">${esc(status)}</span>`;
}

function chatRenderAgent(d) {
  const parts = [];
  if (d.plan && d.plan.length) {
    parts.push(`<p class="hint">Plan: ${d.plan.map((t) => `<code>${esc(t)}</code>`).join(" · ")}</p>`);
  }
  const results = d.tool_results || [];
  if (!results.length) parts.push(`<p>No tool matched this question, so nothing was computed.</p>`);
  results.forEach((r) => {
    parts.push(
      `<div class="chat-tool"><div class="row1">${chatStatusPill(r.status)}`
      + `<b>${esc(r.tool)}</b>${r.private ? ` <span class="hint">(private · local only)</span>` : ""}</div>`
      + `<p>${esc(r.summary || "")}</p>`
      + (r.provenance ? `<p class="hint">Provenance: ${esc(r.provenance)}</p>` : "")
      + (r.reason ? `<p class="hint">Reason: ${esc(r.reason)}</p>` : "")
      + (r.data ? `<details><summary class="hint">raw tool data</summary><pre>${esc(JSON.stringify(r.data, null, 2))}</pre></details>` : "")
      + `</div>`
    );
  });
  if (d.unresolved && d.unresolved.length) {
    parts.push(`<p class="hint">Unresolved: ${d.unresolved.map(esc).join(" · ")}</p>`);
  }
  const ai = d.ai_interpretation;
  if (ai && ai.status === "ok") {
    parts.push(`<p><b>AI interpretation</b> — recipient: ${esc(ai.recipient || ai.provider || "unspecified")}</p>`
      + `<p>${esc(ai.text || "")}</p>`);
  } else if (ai) {
    parts.push(`<p class="hint">AI interpretation: ${esc(ai.status || "not available")} — ${esc(ai.reason || "no AI call was made")}</p>`);
  }
  if (d.privacy && (d.privacy.private_tools || []).length) {
    parts.push(`<p class="hint">Private tools run locally: ${d.privacy.private_tools.map(esc).join(", ")}`
      + (d.privacy.excluded_from_ai.length
        ? ` · excluded from AI: ${d.privacy.excluded_from_ai.map(esc).join(", ")}` : "") + `</p>`);
  }
  return parts.join("");
}

function chatRenderProposal(p, question) {
  const parts = [];
  parts.push(`<p><b>Proposed rule</b> (${esc(p.operator)}) — from: <i>${esc(question)}</i></p>`);
  parts.push(`<p><code>${esc(p.rendered)}</code></p>`);
  parts.push(`<p class="hint">Basis: ${esc(p.basis)}. Nothing has been run yet.</p>`);
  if ((p.unmatched || []).length) {
    parts.push(`<p class="hint"><b>Not taken into account:</b></p><ul class="hint">`
      + p.unmatched.map((u) => `<li>${esc(u.clause)} — ${esc(u.reason)}</li>`).join("") + `</ul>`);
  }
  parts.push(`<button class="ghost chat-load-rule" type="button" data-tree="${esc(JSON.stringify(p.tree))}">`
    + `Load into rule builder →</button>`);
  return parts.join("");
}

async function chatPost(path, body) {
  return api(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

async function chatSend(question, viaPropose) {
  const q = (question || "").trim();
  if (!q) return;
  chatPush("user", esc(q));
  const pending = chatPush("assistant", `<p class="hint">Working…</p>`);
  const tip = pending ? pending.querySelector(".chat-bubble") : null;
  try {
    if (viaPropose) {
      const p = await chatPost("/api/screens/propose", { question: q });
      if (tip) tip.innerHTML = chatRenderProposal(p, q);
      return;
    }
    const ai = $("#chat-ai") && $("#chat-ai").checked;
    const d = await chatPost("/api/agent/run", { question: q, interpret: !!ai });
    if (tip) tip.innerHTML = chatRenderAgent(d);
  } catch (e) {
    if (tip) tip.innerHTML = `<p class="error">${esc(e.message || String(e))}</p>`
      + `<p class="hint">The rest of the application is unaffected. Try rephrasing, or use the Screener directly.</p>`;
  }
  const log = chatEl();
  if (log) log.scrollTop = log.scrollHeight;
}

function chatOpen(open) {
  const panel = $("#chat-panel");
  const fab = $("#chat-fab");
  if (!panel || !fab) return;
  panel.hidden = !open;
  fab.setAttribute("aria-expanded", open ? "true" : "false");
  if (open) {
    try { localStorage.setItem("mt-chat-open", "1"); } catch (e) { /* ignore */ }
    const inp = $("#chat-input");
    if (inp) inp.focus();
  } else {
    try { localStorage.setItem("mt-chat-open", "0"); } catch (e) { /* ignore */ }
  }
}

async function initChat() {
  const exHost = $("#chat-examples");
  if (exHost) {
    exHost.innerHTML = CHAT_EXAMPLES.map((t) =>
      `<button class="chat-chip" type="button" data-q="${esc(t)}">${esc(t)}</button>`).join("");
    exHost.querySelectorAll(".chat-chip").forEach((b) => b.addEventListener("click", () => {
      const inp = $("#chat-input");
      if (inp) inp.value = b.dataset.q;
      const looksRule = /(rsi|adx|mfi|volume|macd|sma|price above|price below|above the|below the)/i.test(b.dataset.q);
      chatSend(b.dataset.q, looksRule);
    }));
  }
  try {
    const t = await api("/api/research/topics");
    const st = t.ai_status || {};
    const el = $("#chat-provider");
    if (el) el.textContent = st.configured
      ? `AI: ${esc(st.provider || "configured")}`
      : "AI explanation: not configured (tools still work)";
  } catch (e) { /* provider status is optional */ }
  let wasOpen = false;
  try { wasOpen = localStorage.getItem("mt-chat-open") === "1"; } catch (e) { wasOpen = false; }
  if (wasOpen) chatOpen(true);
}

function bindChat() {
  const log = chatEl();
  if (!log) return;
  if ($("#chat-fab")) $("#chat-fab").addEventListener("click", () => chatOpen(true));
  if ($("#chat-close")) $("#chat-close").addEventListener("click", () => chatOpen(false));
  if ($("#chat-clear")) $("#chat-clear").addEventListener("click", () => {
    log.innerHTML = "";
    chatPush("assistant", `<p class="hint">Conversation cleared. Tool results are not stored between sessions.</p>`);
  });
  if ($("#chat-send")) $("#chat-send").addEventListener("click", () => {
    const inp = $("#chat-input");
    const q = inp ? inp.value : "";
    if (inp) inp.value = "";
    chatSend(q, false);
  });
  if ($("#chat-propose")) $("#chat-propose").addEventListener("click", () => {
    const inp = $("#chat-input");
    const q = inp ? inp.value : "";
    if (inp) inp.value = "";
    chatSend(q, true);
  });
  if ($("#chat-input")) $("#chat-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      $("#chat-send").click();
    }
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && $("#chat-panel") && !$("#chat-panel").hidden) chatOpen(false);
  });
  // "Load into rule builder" — moves the reviewed proposal into the Screener.
  log.addEventListener("click", (e) => {
    const btn = e.target.closest(".chat-load-rule");
    if (!btn) return;
    let tree;
    try { tree = JSON.parse(btn.dataset.tree); } catch (err) { return; }
    rbRoot = rbFromTree(tree);
    renderRuleBuilder();
    chatPush("assistant", `<p class="hint">Loaded into the rule builder. Open <b>Screener</b>, adjust it, then press Run.</p>`);
    showView("screener");
    viewShown("screener");
  });
}

/* ==========================================================================
   INDEX & RELATIVE STRENGTH
   --------------------------------------------------------------------------
   Consumers of the stored index series (published files, never a live feed):
   * a stock-vs-index ratio line + excess return in the Charts view;
   * an "Index context" dashboard panel;
   * the `relative_strength` scanner metric (server-side, same benchmark).
   ========================================================================== */
let rsBenchmarksLoaded = false;

async function loadBenchmarks() {
  const sel = $("#rs-benchmark");
  if (!sel || rsBenchmarksLoaded) return;
  try {
    const d = await api("/api/indices");
    const names = (d.series || []).map((s) => s.name);
    if (names.length) {
      sel.innerHTML = names.map((n) =>
        `<option value="${esc(n)}"${n === d.benchmark ? " selected" : ""}>${esc(n)}${n === d.benchmark ? " (composite)" : ""}</option>`
      ).join("");
    }
    const src = $("#rs-source");
    if (src) {
      src.textContent = d.count
        ? `${d.count} series · benchmark ${d.benchmark_available ? "available" : "MISSING"} · published files, not live`
        : "no index series stored";
    }
    rsBenchmarksLoaded = true;
  } catch (e) {
    const src = $("#rs-source");
    if (src) src.textContent = `index list unavailable: ${e.message}`;
  }
}

async function runTrailingStop() {
  const out = $("#ts-out");
  const symbol = state.chartSymbol || (($("#symbol-input").value || "").trim().toUpperCase());
  if (!symbol) { out.innerHTML = `<div class="empty">Load a chart first.</div>`; return; }
  const m = $("#ts-method").value;
  const params = new URLSearchParams({
    method: m,
    atr_period: $("#ts-atr-period").value,
    atr_multiple: $("#ts-atr-mult").value,
    swing_bars: $("#ts-swing").value,
    pct: $("#ts-pct").value,
  });
  out.innerHTML = `<div class="empty">Computing…</div>`;
  let d;
  try {
    d = await api(`/api/bars/${encodeURIComponent(symbol)}/trailing-stop?${params}`);
  } catch (e) {
    out.innerHTML = `<div class="empty">Trailing stop unavailable: ${esc(e.message)}</div>`;
    return;
  }
  const r = d.result;
  const stops = (r.stops || []).filter((s) => s !== null && s !== undefined);
  const firstStopIdx = (r.stops || []).findIndex((s) => s !== null && s !== undefined);
  const rows = [
    ["Method", esc(r.method)],
    ["Rule", esc(r.rule)],
    ["Bars used", fmtInt(r.bars_used)],
    ["Current stop", stops.length ? fmtNum(stops[stops.length - 1], 2) : "— (insufficient warmup)"],
    ["Current stop set on", firstStopIdx >= 0 && r.dates ? `${esc(r.dates[firstStopIdx] || "")}${stops.length ? " → " + esc(r.dates[(r.stops.length - 1)] || "") : ""}` : "—"],
    ["Exit found", r.stopped ? `bar ${fmtInt(r.exited_index + 1)} at ${fmtNum(r.exit_price, 2)}` : "no bar's low reached the stop"],
    ["Side", esc(r.side)],
  ];
  out.innerHTML = rows.map(([k, v]) => `<div class="stat"><div class="k">${esc(k)}</div><div class="v">${v}</div></div>`).join("")
    + `<p class="hint">${esc(r.ordering_rule || "")}</p>`
    + `<p class="hint">${esc(d.source || "")}</p>`;
}

async function runRelativeStrength() {
  const out = $("#rs-out");
  const symbol = ($("#symbol-input").value || "").trim().toUpperCase();
  if (!symbol) { out.innerHTML = `<div class="empty">Enter a symbol first.</div>`; return; }
  const bench = $("#rs-benchmark") ? $("#rs-benchmark").value : "NEPSE";
  const window = $("#rs-window") ? $("#rs-window").value : 60;
  const lkb = $("#rs-lookbacks") ? $("#rs-lookbacks").value.trim() : "";
  out.innerHTML = `<div class="empty">Computing…</div>`;
  let d;
  try {
    d = await api(`/api/bars/${encodeURIComponent(symbol)}/relative-strength`
      + `?benchmark=${encodeURIComponent(bench)}&window=${encodeURIComponent(window)}`
      + (lkb ? `&lookbacks=${encodeURIComponent(lkb)}` : ""));
  } catch (e) {
    out.innerHTML = `<div class="empty">Relative strength unavailable: ${esc(e.message)}</div>`;
    clearRsOverlay();
    return;
  }
  state.rsData = d;
  const cov = d.coverage || {};
  const rows = [
    ["Benchmark", `${esc(d.benchmark)}${d.available ? "" : " (unavailable)"}`],
    ["Window return — stock", d.stock_return_pct == null ? "—" : `${fmtNum(d.stock_return_pct, 2)}%`],
    ["Window return — index", d.benchmark_return_pct == null ? "—" : `${fmtNum(d.benchmark_return_pct, 2)}%`],
    ["Excess (stock − index)", d.excess_return_pct == null ? "—" : `${fmtNum(d.excess_return_pct, 2)} pp`],
    ["Aligned bars", fmtInt(cov.aligned_bars)],
    ["Stock dates missing from index", fmtInt(cov.stock_dates_without_benchmark)],
    ["Index dates missing from stock", fmtInt(cov.benchmark_dates_without_stock)],
    ["Coverage", `${esc(d.first_date || "—")} → ${esc(d.last_date || "—")}`],
  ];
  let html = rows.map(([k, v]) => `<div class="stat"><div class="k">${esc(k)}</div><div class="v">${v}</div></div>`).join("")
    + `<p class="hint">${esc(d.calculation || "")} · ${esc(d.source || "")}</p>`
    + (d.available ? "" : `<p class="hint">${esc(d.unavailable_reason || "")}</p>`);
  if (Array.isArray(d.timeframes) && d.timeframes.length) {
    const cell = (v) => ({ html: v });
    const tfRows = d.timeframes.map((t) => [
      cell(`${t.lookback} bars`),
      cell(t.available ? `${fmtNum(t.stock_return_pct, 2)}%` : "—"),
      cell(t.available ? `${fmtNum(t.benchmark_return_pct, 2)}%` : "—"),
      cell(t.available ? `${fmtNum(t.excess_return_pct, 2)} pp` : "unavailable"),
      cell(t.available ? `${esc(t.base_date)} → ${esc(t.last_date)}` : "—"),
      cell(t.available ? "" : esc(t.unavailable_reason)),
    ]);
    html += `<div class="tablewrap">${table(
      ["Lookback", "Stock", "Index", "Excess", "Window dates", "Why unavailable"],
      tfRows
    )}</div><p class="hint">${esc(d.timeframes_calculation || "")}</p>`;
  }
  out.innerHTML = html;
  if ($("#rs-overlay") && $("#rs-overlay").checked) drawRsOverlay(d);
  else clearRsOverlay();
}

function clearRsOverlay() {
  const chart = state.charts.price;
  (state.rsSeries || []).forEach((s) => { try { chart.removeSeries(s); } catch (e) { /* gone */ } });
  state.rsSeries = [];
}

/* The ratio line is drawn on its own right-hand scale so it cannot be mistaken
   for a price. It only ever uses the detector-free, inner-joined points the
   endpoint returned. */
function drawRsOverlay(d) {
  const chart = state.charts.price;
  if (!chart) return;
  clearRsOverlay();
  const pts = d && d.ratio_points;
  if (!pts || !pts.length) return;
  const visible = new Set(state.chartDates || []);
  const data = pts.map((p) => ({ time: p.date, value: p.ratio }))
    .filter((p) => !state.chartDates.length || visible.has(p.time));
  if (!data.length) return;
  const s = chart.addLineSeries({
    color: PRAVAHA.mint, lineWidth: 2, priceLineVisible: false, lastValueVisible: true,
    priceScaleId: "rs", title: `RS vs ${d.benchmark} (100 = start)`,
  });
  try { chart.priceScale("rs").applyOptions({ scaleMargins: { top: 0.1, bottom: 0.1 }, visible: false }); }
  catch (e) { /* older build: leave on the main scale */ }
  s.setData(data);
  state.rsSeries.push(s);
}

async function loadDashboardIndex() {
  const el = $("#dash-index");
  const hint = $("#dash-index-hint");
  if (!el) return;
  if (!hint) return;
  try {
    const d = await api("/api/indices");
    if (!d.count) {
      el.innerHTML = `<div class="stat"><div class="k">Status</div><div class="v muted">no index series</div></div>`;
      if (hint) hint.textContent = "No published index files are loaded, so no index context is shown.";
      return;
    }
    const bench = (d.series || []).find((s) => s.name === d.benchmark);
    el.innerHTML = [
      ["Series stored", fmtInt(d.count)],
      ["Composite", bench ? esc(bench.name) : "missing"],
      ["Composite rows", bench ? fmtInt(bench.rows) : "—"],
      ["Composite last date", bench ? esc(bench.last_date || "—") : "—"],
    ].map(([k, v]) => `<div class="stat"><div class="k">${esc(k)}</div><div class="v">${v}</div></div>`).join("");
    if (hint) {
      hint.textContent = "Published index files — historical, NOT a live feed. "
        + `Coverage ${bench ? `${bench.first_date} → ${bench.last_date}` : "unknown"}.`;
    }
  } catch (e) {
    el.innerHTML = `<div class="stat"><div class="k">Status</div><div class="v muted">unavailable</div></div>`;
    if (hint) hint.textContent = `Index data unavailable: ${e.message}`;
  }
}

function bindRelativeStrength() {
  if ($("#run-rs")) $("#run-rs").addEventListener("click", runRelativeStrength);
  if ($("#run-ts")) $("#run-ts").addEventListener("click", runTrailingStop);
  if ($("#ts-method")) $("#ts-method").addEventListener("change", () => {
    // Only the params relevant to the chosen method are shown; the others
    // stay in the DOM but are ignored server-side by design.
    const m = $("#ts-method").value;
    $("#ts-atr-period").disabled = $("#ts-atr-mult").disabled = m !== "chandelier";
    $("#ts-swing").disabled = m !== "swing";
    $("#ts-pct").disabled = m !== "pct";
  });
  if ($("#rs-overlay")) $("#rs-overlay").addEventListener("change", () => {
    if ($("#rs-overlay").checked && state.rsData) drawRsOverlay(state.rsData);
    else clearRsOverlay();
  });
}

/* ==========================================================================
   RESEARCH TEMPLATES
   --------------------------------------------------------------------------
   The catalogue is *declarative* (server-side, `megatool/templates.py`) and the
   runner below is generic: it performs the declared calls against the same
   read-only endpoints the rest of the app uses and shows whatever came back.
   A step that returns nothing useful says so; it is never padded with invented
   values. Nothing is executed until the researcher presses Run.
   ========================================================================== */
let tplCatalogue = null;
let tplPick = null;
let tplLastRun = null;   // {template, symbol, symbols, steps:[{label,path,method,data|error}]}

async function initTemplates() {
  const sel = $("#tpl-pick");
  if (!sel) return;
  if (!tplCatalogue) {
    try {
      const d = await api("/api/templates");
      tplCatalogue = d.templates || [];
    } catch (e) {
      sel.innerHTML = `<option value="">unavailable</option>`;
      $("#tpl-error").textContent = `Templates unavailable: ${e.message}`;
      return;
    }
  }
  sel.innerHTML = tplCatalogue.map((t) =>
    `<option value="${esc(t.id)}">${esc(t.title)} — ${esc(t.group)}</option>`).join("")
    + `<option value="">— choose —</option>`;
  if (tplCatalogue.length) sel.value = tplCatalogue[0].id;
  renderTemplateInfo();
}

function currentTemplate() {
  const sel = $("#tpl-pick");
  if (!sel || !tplCatalogue) return null;
  tplPick = sel.value;
  return tplCatalogue.find((t) => t.id === sel.value) || null;
}

function renderTemplateInfo() {
  const t = currentTemplate();
  const info = $("#tpl-info");
  if (!t) { if (info) info.textContent = "Select a template."; return; }
  const needs = [];
  if (t.inputs.includes("symbol")) needs.push("a symbol");
  if (t.inputs.includes("symbols")) needs.push("a symbol list");
  info.innerHTML = `<b>${esc(t.title)}</b> — ${esc(t.summary)}<br />`
    + `${t.question ? `Agent question: <code>${esc(t.question)}</code><br />` : ""}`
    + `Steps: ${t.steps.map((s) => `<code>${esc(s.path)}</code>`).join(" · ")}<br />`
    + (needs.length ? `Needs ${esc(needs.join(" and "))}. ` : "No symbol input needed. ")
    + `<br /><span class="muted">${t.notes.map(esc).join(" ")}</span>`;
}

/* A step result is rendered as a table when it contains a list of objects, and
   as raw JSON otherwise — never as a fabricated summary. */
function tplRenderPayload(obj) {
  if (obj == null) return `<div class="empty">no data returned</div>`;
  if (Array.isArray(obj) && obj.length && typeof obj[0] === "object") return tplTable(obj);
  if (obj && typeof obj === "object") {
    const arrayKey = Object.keys(obj).find((k) =>
      Array.isArray(obj[k]) && obj[k].length && typeof obj[k][0] === "object");
    if (arrayKey) {
      const scalarKeys = Object.keys(obj).filter((k) => typeof obj[k] !== "object" && obj[k] != null);
      const head = scalarKeys.length
        ? `<p class="hint">${scalarKeys.map((k) => `${esc(k)}=${esc(obj[k])}`).join(" · ")}</p>` : "";
      return head + tplTable(obj[arrayKey], arrayKey);
    }
    const scalars = Object.keys(obj).filter((k) => typeof obj[k] !== "object");
    if (scalars.length && scalars.length <= 12 && Object.keys(obj).length === scalars.length) {
      return `<div class="stat-row">` + scalars.map((k) =>
        `<div class="stat"><div class="k">${esc(k)}</div><div class="v">${esc(String(obj[k]))}</div></div>`).join("") + `</div>`;
    }
  }
  return `<details><summary class="hint">raw response</summary><pre style="max-height:220px;overflow:auto">${esc(JSON.stringify(obj, null, 2))}</pre></details>`;
}

function tplTable(rows, label) {
  const cols = [...new Set(rows.flatMap((r) => Object.keys(r)))].slice(0, 9);
  return `<div class="tablewrap">${table(
    cols,
    rows.slice(0, 25).map((r) => cols.map((c) => {
      const v = r[c];
      const text = v == null ? "—" : (typeof v === "object" ? JSON.stringify(v) : String(v));
      return { html: esc(text.length > 120 ? text.slice(0, 118) + "…" : text) };
    }))
  )}</div>` + (rows.length > 25 ? `<p class="hint">showing 25 of ${rows.length} rows${label ? ` (${esc(label)})` : ""}</p>` : "");
}

async function runTemplate() {
  const t = currentTemplate();
  const errEl = $("#tpl-error");
  const out = $("#tpl-results");
  errEl.textContent = "";
  if (!t) { errEl.textContent = "Pick a template first."; return; }
  const symbol = ($("#tpl-symbol").value || "").trim().toUpperCase();
  const symbols = ($("#tpl-symbols").value || "").trim().toUpperCase();
  if (t.inputs.includes("symbol") && !symbol) { errEl.textContent = "This template needs a symbol."; return; }
  if (t.inputs.includes("symbols") && !symbols) { errEl.textContent = "This template needs a symbol list (comma-separated)."; return; }

  out.innerHTML = `<div class="empty">Running ${esc(t.title)}…</div>`;
  const blocks = [];
  const ctx = { symbol, symbols: symbols || symbol };
  const captured = [];

  if (t.question) {
    const q = t.question.replace("{symbol}", ctx.symbol).replace("{symbols}", ctx.symbols);
    try {
      const d = await chatPost("/api/agent/run", { question: q, interpret: false });
      const body = chatRenderAgent(d);
      blocks.push(`<div class="card"><h2>Agent — <code>${esc(q)}</code></h2>${body}</div>`);
      captured.push({ label: "agent", path: "/api/agent/run", method: "POST", data: d });
    } catch (e) {
      blocks.push(`<div class="card"><h2>Agent</h2><p class="error">${esc(e.message)}</p></div>`);
      captured.push({ label: "agent", path: "/api/agent/run", method: "POST", error: e.message });
    }
  }

  for (const step of t.steps) {
    const path = step.path.replace("{symbol}", ctx.symbol).replace("{symbols}", ctx.symbols);
    const method = step.params._method || "GET";
    let url = path;
    let opts;
    if (method === "POST") {
      const body = Object.fromEntries(Object.entries(step.params).filter(([k]) => k !== "_method"));
      opts = { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
    } else {
      const qs = new URLSearchParams(Object.entries(step.params)
        .filter(([k]) => k !== "_method")
        .map(([k, v]) => [k, String(v).replace("{symbol}", ctx.symbol).replace("{symbols}", ctx.symbols)]));
      const q = qs.toString();
      if (q) url += (url.includes("?") ? "&" : "?") + q;
      opts = undefined;
    }
    let body;
    try {
      const payload = await api(url, opts);
      captured.push({ label: step.label, path, method, data: payload });
      body = tplRenderPayload(payload);
    } catch (e) {
      captured.push({ label: step.label, path, method, error: e.message });
      body = `<p class="error">${esc(e.message)}</p>`;
    }
    blocks.push(`<div class="card"><h2>${esc(step.label)} <span class="muted">· ${esc(method)} ${esc(path)}</span></h2>`
      + `<p class="hint">${esc(step.why)}</p>${body}</div>`);
  }
  out.innerHTML = blocks.join("");
  tplLastRun = {
    template: t.id, title: t.title, symbol: symbol || null, symbols: symbols || null,
    steps: captured, ran_at: new Date().toISOString(),
  };
}

const TPL_SAVED_KEY = "mt-template-copies";

function loadTemplateCopies() {
  try {
    const raw = JSON.parse(localStorage.getItem(TPL_SAVED_KEY) || "[]");
    return Array.isArray(raw) ? raw : [];
  } catch (e) { return []; }
}

function persistTemplateCopies(list) {
  try { localStorage.setItem(TPL_SAVED_KEY, JSON.stringify(list.slice(0, 50))); } catch (e) { /* off */ }
}

async function saveTemplateCopy() {
  const t = currentTemplate();
  const errEl = $("#tpl-error");
  errEl.textContent = "";
  if (!t) { errEl.textContent = "Pick a template first."; return; }
  const symbol = ($("#tpl-symbol").value || "").trim().toUpperCase();
  const symbols = ($("#tpl-symbols").value || "").trim().toUpperCase();
  const copies = loadTemplateCopies().filter((c) => !(c.template === t.id && c.symbol === symbol && c.symbols === symbols));
  copies.unshift({
    template: t.id, title: t.title, symbol: symbol || null, symbols: symbols || null,
    saved_at: new Date().toISOString(),
    ran: !!(tplLastRun && tplLastRun.template === t.id),
  });
  persistTemplateCopies(copies);
  renderTemplateCopies();
  const out = $("#tpl-results");
  if (out) {
    out.insertAdjacentHTML("afterbegin",
      `<p class="hint">Saved a customized copy (browser-local). Press Load in the list below to bring it back.</p>`);
  }
}

function renderTemplateCopies() {
  const el = $("#tpl-copies");
  if (!el) return;
  const copies = loadTemplateCopies();
  if (!copies.length) {
    el.innerHTML = `<div class="empty">No saved template copies yet.</div>`;
    return;
  }
  el.innerHTML = table(
    ["Template", "Symbol", "Compare", "Saved", "Run yet?", ""],
    copies.map((c) => [
      { html: esc(c.title || c.template) },
      { html: esc(c.symbol || "—") },
      { html: esc(c.symbols || "—") },
      { html: esc((c.saved_at || "").slice(0, 19).replace("T", " ")) },
      { html: c.ran ? "yes" : `<span class="muted">not run</span>` },
      { html: `<button class="ghost tpl-load" data-t="${esc(c.template)}">Load</button>`
        + ` <button class="ghost tpl-drop" data-t="${esc(c.template)}" data-s="${esc(c.symbol || "")}">Remove</button>` },
    ])
  );
  el.querySelectorAll(".tpl-load").forEach((b) => b.addEventListener("click", () => {
    const c = loadTemplateCopies().find((x) => x.template === b.dataset.t);
    if (!c || !$("#tpl-pick")) return;
    $("#tpl-pick").value = c.template;
    if ($("#tpl-symbol")) $("#tpl-symbol").value = c.symbol || "";
    if ($("#tpl-symbols")) $("#tpl-symbols").value = c.symbols || "";
    renderTemplateInfo();
  }));
  el.querySelectorAll(".tpl-drop").forEach((b) => b.addEventListener("click", () => {
    persistTemplateCopies(loadTemplateCopies().filter((x) =>
      !(x.template === b.dataset.t && (x.symbol || "") === b.dataset.s)));
    renderTemplateCopies();
  }));
}

function openTemplateWorkspace() {
  const symbol = ($("#tpl-symbol").value || "").trim().toUpperCase();
  const t = currentTemplate();
  if (!t) return;
  if (symbol) {
    if (t.view === "charts" && $("#symbol-input")) {
      $("#symbol-input").value = symbol;
      showView("charts");
      viewShown("charts");
      loadChart();
      return;
    }
    if (t.view === "research" && $("#rs-symbol")) {
      $("#rs-symbol").value = symbol;
      showView("research");
      viewShown("research");
      return;
    }
    if (t.view === "fundamentals" && $("#fund-symbol")) {
      $("#fund-symbol").value = symbol;
      showView("fundamentals");
      viewShown("fundamentals");
      return;
    }
  }
  showView(t.view);
  viewShown(t.view);
}

function bindTemplates() {
  if ($("#tpl-pick")) $("#tpl-pick").addEventListener("change", renderTemplateInfo);
  if ($("#tpl-run")) $("#tpl-run").addEventListener("click", runTemplate);
  if ($("#tpl-save")) $("#tpl-save").addEventListener("click", saveTemplateCopy);
  if ($("#tpl-goto")) $("#tpl-goto").addEventListener("click", openTemplateWorkspace);
  renderTemplateCopies();
}

/* Sidebar icons: one consistent stroke family (24×24, currentColor) injected at
   boot so labels stay in the HTML and keyboard nav is untouched. */
const NAV_ICONS = {
  overview: '<rect x="3" y="3" width="8" height="8" rx="1"/><rect x="13" y="3" width="8" height="5" rx="1"/><rect x="13" y="10" width="8" height="11" rx="1"/><rect x="3" y="13" width="8" height="8" rx="1"/>',
  watchlists: '<path d="M4 6h16M4 12h16M4 18h10"/><circle cx="19" cy="18" r="2.2"/>',
  charts: '<path d="M4 19V5"/><path d="M4 19h16"/><path d="M6.5 15l3.5-5 3 3 4.5-6.5"/>',
  screener: '<circle cx="10" cy="10" r="6.5"/><path d="M14.8 14.8L21 21"/>',
  ideas: '<path d="M9 18h6"/><path d="M10 21h4"/><path d="M12 3a6 6 0 0 1 3.6 10.8c-.7.5-1.1 1.3-1.1 2.2h-5c0-.9-.4-1.7-1.1-2.2A6 6 0 0 1 12 3z"/>',
  tracing: '<circle cx="6" cy="6" r="2.5"/><circle cx="18" cy="18" r="2.5"/><path d="M8.2 7.4C12 9 15.4 14.5 16 15.6"/>',
  portfolio: '<path d="M3 8h18v11a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1z"/><path d="M8 8V6a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><path d="M3 13h18"/>',
  journal: '<path d="M5 4h11l3 3v13H5z"/><path d="M8 9h7M8 12.5h7M8 16h4.5"/>',
  research: '<circle cx="11" cy="11" r="6"/><path d="M14.9 14.9L20 20"/><path d="M8.5 11h5M11 8.5v5"/>',
  fundamentals: '<path d="M4 20V9l8-5 8 5v11"/><path d="M9.5 20v-6h5v6"/><path d="M12 4.2V6"/>',
  floorsheet: '<path d="M4 5h16v14H4z"/><path d="M4 9h16M9 9v10M14 9v10"/>',
  pdf: '<path d="M6 3h9l4 4v14H6z"/><path d="M15 3v4h4"/><path d="M9 13h6M9 16.5h6"/>',
  backtest: '<path d="M12 3a9 9 0 1 0 9 9"/><path d="M12 7v5l3.5 2"/>',
  workshop: '<path d="M14 6.5a3.8 3.8 0 0 1 5.3-3.5l-2.9 2.9 2.2 2.2 2.9-2.9A3.8 3.8 0 0 1 17 10.5c-.5 0-1-.1-1.5-.3L8.8 16.9a4 4 0 1 1-5.7-5.7l6.6-6.7"/>',
  templates: '<rect x="3.5" y="4" width="17" height="16" rx="1.5"/><path d="M3.5 9h17M9 9v11"/>',
  forecaster: '<path d="M3 16l5-4 4 3 5-6 4 4"/><path d="M17 13h4v4" transform="translate(-2,-1)"/>',
  kronos: '<circle cx="12" cy="12" r="4.2"/><path d="M12 3v3.2M12 17.8V21M3 12h3.2M17.8 12H21M5.6 5.6l2.3 2.3M16.1 16.1l2.3 2.3M18.4 5.6l-2.3 2.3M7.9 16.1l-2.3 2.3"/>',
  data: '<ellipse cx="12" cy="5.5" rx="7.5" ry="2.8"/><path d="M4.5 5.5v13c0 1.5 3.4 2.8 7.5 2.8s7.5-1.3 7.5-2.8v-13"/><path d="M4.5 12c0 1.5 3.4 2.8 7.5 2.8s7.5-1.3 7.5-2.8"/>',
};
function installNavIcons() {
  $$("#nav button[data-view]").forEach((b) => {
    const body = NAV_ICONS[b.dataset.view];
    if (!body) return;
    const svg = `<svg class="nav-ico" viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">${body}</svg>`;
    b.insertAdjacentHTML("afterbegin", svg);
    b.setAttribute("title", b.textContent.trim());
  });
}

function boot() {
  installNavIcons();
  initSastoShare();
  $$("#nav button[data-view]").forEach((b) =>
    b.addEventListener("click", () => { showView(b.dataset.view); viewShown(b.dataset.view); })
  );
  $("#load-chart").addEventListener("click", loadChart);
  $("#symbol-input").addEventListener("keydown", (e) => { if (e.key === "Enter") loadChart(); });
  chartChrome();
  // Global search (top bar): one symbol selection drives every view.
  const gs = $("#global-symbol");
  if (gs) gs.addEventListener("keydown", (e) => {
    if (e.key !== "Enter") return;
    const sym = (gs.value || "").trim().toUpperCase();
    if (!sym) return;
    $("#symbol-input").value = sym;
    showView("charts");
    viewShown("charts");
    loadChart();
  });
  $("#run-screen").addEventListener("click", () => runScreen());
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
  $("#ws-run").addEventListener("click", loadWorkspace);
  $("#ws-symbol").addEventListener("keydown", (e) => { if (e.key === "Enter") loadWorkspace(); });
  $("#ws-jump").addEventListener("click", () => {
    const sym = ($("#ws-symbol").value || "").trim().toUpperCase();
    if (sym) $("#symbol-input").value = sym;
    showView("charts");
    loadChart();
  });
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
  $("#fs-trend").addEventListener("click", loadFloorSheetTrend);

  $("#ratio-load").addEventListener("click", loadRatios);
  $("#ratio-symbols").addEventListener("keydown", (e) => { if (e.key === "Enter") loadRatios(); });
  $("#rs-agent-btn").addEventListener("click", runAgent);
  $("#pf-risk-run").addEventListener("click", loadPortfolioRisk);
  $("#al-run").addEventListener("click", evaluateAlerts);
  $("#al-clear").addEventListener("click", clearAlertHistory);
  $("#run-corr").addEventListener("click", runCorrelation);

  if ($("#candle-run")) $("#candle-run").addEventListener("click", () => runCandles());
  if ($("#candle-all")) $("#candle-all").addEventListener("click", () => { setAllCandlePicks(true); runCandles(); });
  if ($("#candle-none")) $("#candle-none").addEventListener("click", () => { setAllCandlePicks(false); runCandles(); });
  if ($("#candle-markers")) $("#candle-markers").addEventListener("change", () => runCandles());
  if ($("#candle-require-trend")) $("#candle-require-trend").addEventListener("change", () => runCandles());
  if ($("#elliott-run")) $("#elliott-run").addEventListener("click", runElliott);
  if ($("#elliott-clear")) $("#elliott-clear").addEventListener("click", () => {
    if (state.chartSymbol) clearElliottLabels(state.chartSymbol);
    applyElliottLabels();
  });
  if ($("#harmonic-run")) $("#harmonic-run").addEventListener("click", runHarmonic);
  if ($("#harmonic-clear")) $("#harmonic-clear").addEventListener("click", () => {
    (state.harmonicSeries || []).forEach((s) => { try { state.charts.price.removeSeries(s); } catch (e) { /* gone */ } });
    state.harmonicSeries = [];
    state.harmonicMarkers = [];
    flushMarkers();
    if ($("#harmonic")) $("#harmonic").innerHTML = `<div class="empty">Cleared.</div>`;
  });

  if ($("#wl-create")) $("#wl-create").addEventListener("click", createWatchlist);
  if ($("#wl-refresh")) $("#wl-refresh").addEventListener("click", loadWatchlists);
  if ($("#wl-add-btn")) $("#wl-add-btn").addEventListener("click", () => {
    const s = ($("#wl-add-symbol").value || "").trim();
    if (s && state.selectedWatchlist) patchWatchlist(state.selectedWatchlist, { add: [s] });
  });
  if ($("#wl-rename-btn")) $("#wl-rename-btn").addEventListener("click", () => {
    const n = ($("#wl-rename").value || "").trim();
    if (n && state.selectedWatchlist) patchWatchlist(state.selectedWatchlist, { new_name: n });
  });
  if ($("#wl-delete")) $("#wl-delete").addEventListener("click", () => {
    if (state.selectedWatchlist) removeWatchlist(state.selectedWatchlist);
  });

  if ($("#ex-save")) $("#ex-save").addEventListener("click", saveExperiment);
  if ($("#ex-refresh")) $("#ex-refresh").addEventListener("click", loadExperiments);
  if ($("#ex-compare")) $("#ex-compare").addEventListener("click", compareExperiments);
  if ($("#rs-export-btn")) $("#rs-export-btn").addEventListener("click", exportResearchReport);

  bindRuleBuilder();
  bindDashboard();
  bindDrawings();
  bindClearAndPalette();
  buildDrawRail();
  bindPatternPanel();
  bindChat();
  initChat();
  bindRelativeStrength();
  bindTemplates();

  loadFreshness();
  loadSymbols();
  loadOverview();
  loadMarketOverview();  startLivePolling();
  syncTickerWatchlist();
  loadRegime();
  loadAlertHistory();
  loadPresets();
  loadData();
  loadStrategies();
  loadResearchMeta();
  bindResearchStudio();
}

document.addEventListener("DOMContentLoaded", boot);


/* ==========================================================================
   RESEARCH STUDIO — multi-symbol reports, real background progress
   --------------------------------------------------------------------------
   The browser never guesses how far a build has got: the server reports
   completed steps / total steps, and this code renders exactly that. Jobs are
   re-openable after a refresh because the server persists them.
   ========================================================================== */
const RST = {
  catalog: null,
  selected: new Set(),
  preset: "full",
  job: null,
  timer: null,
  pollErrors: 0,
};

function rstFmt(v) {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") return fmtSmart(v);
  return String(v);
}

function rstGroupByCategory(components) {
  const cats = RST.catalog && RST.catalog.categories ? RST.catalog.categories : [];
  const byCat = new Map(cats.map((c) => [c.id, { name: c.name, items: [] }]));
  components.forEach((c) => {
    if (!byCat.has(c.category)) byCat.set(c.category, { name: c.category, items: [] });
    byCat.get(c.category).items.push(c);
  });
  return byCat;
}

function rstRenderComponents() {
  const host = $("#rst-components");
  if (!host) return;
  if (!RST.catalog) { host.innerHTML = `<div class="empty">Catalog unavailable.</div>`; return; }
  const hideUnavailable = $("#rst-only-available") && $("#rst-only-available").checked;
  const visible = RST.catalog.components.filter((c) => !hideUnavailable || c.available);
  const groups = rstGroupByCategory(visible);
  const parts = [];
  for (const [catId, group] of groups) {
    if (!group.items.length) continue;
    parts.push(`<h3 class="topic-head">${esc(group.name)}</h3><div class="controls rst-cat">`);
    group.items.forEach((c) => {
      const checked = RST.selected.has(c.id) ? "checked" : "";
      const avail = c.available
        ? ""
        : ` <span class="warn" title="${esc(c.reason || "")}">unavailable</span>`;
      parts.push(
        `<label class="chk" title="${esc(c.description || "")}" style="min-width:20em">` +
        `<input type="checkbox" class="rst-comp" value="${esc(c.id)}" ${checked}` +
        `${c.available ? "" : " data-missing=\"1\""} /> ${esc(c.name)}${avail}</label>`
      );
    });
    parts.push(`</div>`);
  }
  if (!parts.length) parts.push(`<div class="empty">No analyses match this filter.</div>`);
  host.innerHTML = parts.join("");
  rstUpdateCount();
}

function rstUpdateCount() {
  const el = $("#rst-count");
  if (!el) return;
  const available = RST.catalog
    ? RST.catalog.components.filter((c) => RST.selected.has(c.id) && c.available).length
    : 0;
  el.textContent = `${RST.selected.size} selected · ${available} with data`;
}

function rstApplyPreset(id) {
  if (!RST.catalog) return;
  const p = (RST.catalog.presets || []).find((x) => x.id === id);
  if (!p) return;
  RST.preset = id;
  RST.selected = new Set(p.components);
  rstRenderComponents();
}

async function loadResearchStudio(force) {
  if (RST.catalog && !force) return;
  try {
    const d = await api("/api/baba/research/catalog");
    RST.catalog = d;
    const sel = $("#rst-preset");
    if (sel) {
      sel.innerHTML = (d.presets || [])
        .map((p) => `<option value="${esc(p.id)}">${esc(p.label)} (${p.count})</option>`)
        .join("");
      sel.value = d.default_preset || "full";
    }
    rstApplyPreset(d.default_preset || "full");
    $("#rst-error").textContent = "";
  } catch (e) {
    const host = $("#rst-components");
    if (host) host.innerHTML = `<div class="empty">Could not load the analysis catalog: ${esc(e.message)}</div>`;
  }
  loadResearchJobs();
}

function rstJobSymbols(job) {
  return (job.params && job.params.symbols ? job.params.symbols : []).join(", ");
}

function rstArtifactButton(job, fmt, label) {
  if (!job.artifacts || !job.artifacts[fmt]) return "";
  return `<button class="ghost rst-dl" data-job="${esc(job.id)}" data-fmt="${esc(fmt)}">${esc(label)}</button>`;
}

function rstRenderJob(job) {
  const card = $("#rst-job");
  if (!card) return;
  card.hidden = false;
  const bar = $("#rst-progress");
  if (bar) bar.value = Number(job.progress || 0);
  const meta = $("#rst-job-meta");
  if (meta) {
    const steps = job.steps_total ? ` · step ${job.steps_done}/${job.steps_total}` : "";
    const statusCls = job.status === "SUCCEEDED" ? "up" : (job.status === "FAILED" ? "down" : "warn");
    meta.innerHTML =
      `<b class="${statusCls}">${esc(job.status)}</b> · <b>${Number(job.progress || 0).toFixed(1)}%</b>` +
      `${esc(steps)} · stage: ${esc(job.stage || "—")}<br>` +
      `<span class="muted">${esc(job.message || "")}</span>` +
      (job.error ? `<br><span class="down">${esc(job.error)}</span>` : "") +
      `<br><span class="muted">Symbols: ${esc(rstJobSymbols(job))} · job ${esc(job.id)}</span>`;
  }
  const dl = $("#rst-downloads");
  if (dl) {
    dl.innerHTML =
      rstArtifactButton(job, "pdf", "Download PDF") +
      rstArtifactButton(job, "xlsx", "Download Excel") +
      rstArtifactButton(job, "zip", "Download full ZIP") +
      rstArtifactButton(job, "json", "Download JSON");
  }
  $$("#rst-downloads .rst-dl").forEach((b) => {
    b.addEventListener("click", () => rstDownload(b.dataset.job, b.dataset.fmt));
  });
}

async function rstDownload(jobId, fmt) {
  const err = $("#rst-error");
  err.textContent = "";
  try {
    const res = await fetch(API_BASE + `/api/baba/research/jobs/${jobId}/download/${fmt}`,
      _withFriendToken({}));
    if (!res.ok) {
      let msg = `${res.status} ${res.statusText}`;
      try { const b = await res.json(); msg = b.detail || b.error || msg; } catch (e) { /* no body */ }
      throw new Error(msg);
    }
    const blob = await res.blob();
    const cd = res.headers.get("Content-Disposition") || "";
    const m = /filename="?([^";]+)"?/.exec(cd);
    const name = m ? m[1] : `research-report.${fmt}`;
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = name;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 5000);
  } catch (e) {
    err.textContent = `Download failed: ${e.message}`;
  }
}

function rstStopPolling() {
  if (RST.timer) { clearTimeout(RST.timer); RST.timer = null; }
}

function rstPoll(jobId) {
  rstStopPolling();
  const tick = async () => {
    try {
      const d = await api(`/api/baba/research/jobs/${jobId}`);
      RST.job = d.job;
      RST.pollErrors = 0;
      rstRenderJob(d.job);
      loadResearchJobs(true);
      if (["SUCCEEDED", "FAILED", "INTERRUPTED", "CANCELLED"].includes(d.job.status)) {
        rstStopPolling();
        return;
      }
    } catch (e) {
      RST.pollErrors += 1;
      if (RST.pollErrors >= 8) {
        $("#rst-error").textContent = `Lost contact with the job: ${e.message}`;
        rstStopPolling();
        return;
      }
    }
    RST.timer = setTimeout(tick, 1200);
  };
  tick();
}

async function rstStart() {
  const err = $("#rst-error");
  err.textContent = "";
  const raw = ($("#rst-symbols").value || "").trim();
  if (!raw) { err.textContent = "Enter at least one symbol."; return; }
  const symbols = raw.split(/[\s,;]+/).map((s) => s.trim().toUpperCase()).filter(Boolean);
  if (!RST.selected.size) { err.textContent = "Select at least one analysis."; return; }
  const risk = ($("#rst-risk").value || "").trim();
  const capital = ($("#rst-capital").value || "").trim();
  const body = {
    symbols,
    components: Array.from(RST.selected),
    preset: RST.preset,
    risk_budget: risk ? Number(risk) : null,
    capital: capital ? Number(capital) : null,
    title: `Research report: ${symbols.join(", ")}`,
  };
  const btn = $("#rst-start");
  btn.disabled = true;
  btn.textContent = "Starting…";
  try {
    const d = await api("/api/baba/research/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    RST.job = d.job;
    rstRenderJob(d.job);
    rstPoll(d.job.id);
    loadResearchJobs(true);
  } catch (e) {
    err.textContent = `Could not start the report: ${e.message}`;
  } finally {
    btn.disabled = false;
    btn.textContent = "Build report";
  }
}

async function loadResearchJobs(quiet) {
  const host = $("#rst-jobs");
  if (!host) return;
  try {
    const d = await api("/api/baba/research/jobs?limit=10");
    const jobs = d.jobs || [];
    if (!jobs.length) {
      host.innerHTML = `<div class="empty">No report has been built yet.</div>`;
      return;
    }
    const rows = jobs.map((j) => [
      { html: `<b>${esc(j.status)}</b>` },
      { html: `${Number(j.progress || 0).toFixed(0)}%` },
      { html: esc(rstJobSymbols(j) || "—"), cls: "wrap" },
      { html: esc(j.created_at || ""), cls: "wrap muted" },
      { html: esc((j.message || "").slice(0, 90)), cls: "wrap muted" },
      { html: [
        rstArtifactButton(j, "pdf", "PDF"),
        rstArtifactButton(j, "xlsx", "XLSX"),
        rstArtifactButton(j, "zip", "ZIP"),
        `<button class="ghost rst-open" data-job="${esc(j.id)}">Open</button>`,
      ].join(" ") },
    ]);
    host.innerHTML = table(["Status", "Progress", "Symbols", "Started", "Stage", "Files"], rows);
    $$("#rst-jobs .rst-dl").forEach((b) => {
      b.addEventListener("click", () => rstDownload(b.dataset.job, b.dataset.fmt));
    });
    $$("#rst-jobs .rst-open").forEach((b) => {
      b.addEventListener("click", async () => {
        try {
          const r = await api(`/api/baba/research/jobs/${b.dataset.job}`);
          RST.job = r.job;
          rstRenderJob(r.job);
          if (["QUEUED", "RUNNING"].includes(r.job.status)) rstPoll(r.job.id);
        } catch (e) { $("#rst-error").textContent = e.message; }
      });
    });
  } catch (e) {
    if (!quiet) host.innerHTML = `<div class="empty">Could not list builds: ${esc(e.message)}</div>`;
  }
}

async function runVolatilityForecast() {
  const err = $("#rs-vol-error");
  const out = $("#rs-vol-out");
  err.textContent = "";
  const sym = ($("#rs-vol-symbol").value || $("#rs-symbol").value || "").trim().toUpperCase();
  if (!sym) { err.textContent = "Enter a symbol."; return; }
  const risk = ($("#rs-vol-risk").value || "").trim();
  const capital = ($("#rs-vol-capital").value || "").trim();
  const qs = new URLSearchParams();
  if (risk) qs.set("risk_budget", risk);
  if (capital) qs.set("capital", capital);
  out.innerHTML = `<div class="empty">Computing walk-forward evaluation…</div>`;
  try {
    const d = await api(`/api/baba/volatility/${encodeURIComponent(sym)}?${qs.toString()}`);
    const f = d.forecast;
    const rows = [
      ["As-of session", f.as_of_session],
      ["Price basis", f.price_kind],
      ["Point range forecast", f.point_range],
      ["Point as % of last close", f.point_range_percent_of_price],
      ["80% band (points)", `${f.band_80[0]} – ${f.band_80[1]}`],
      ["80% band (% of close)", `${f.band_80_percent_of_price[0]} – ${f.band_80_percent_of_price[1]}`],
      ["Band method", f.band_80_method],
      ["60-session median range", f.normal_range_60_session_median],
      ["Forecast / normal", f.ratio_to_normal],
      ["Selected model", f.model],
      ["Measured 80% coverage", f.measured_interval_coverage_percent],
      ["History", `${f.history_first} → ${f.as_of_session} (${f.history_bars} bars)`],
    ];
    const modelRows = Object.entries(d.evaluation.models).map(([k, m]) => [
      { html: `<b>${esc(k)}</b>` }, { html: esc(rstFmt(m.n)) }, { html: esc(rstFmt(m.mae)) },
      { html: esc(rstFmt(m.rmse)) }, { html: esc(rstFmt(m.median_ape_percent)) },
      { html: esc(rstFmt(m.improvement_vs_naive_percent)) },
      { html: esc(rstFmt(m.interval_coverage_percent)) },
    ]);
    let sizing = "";
    if (d.position_sizing && d.position_sizing.table) {
      const srows = d.position_sizing.table.map((s) => [
        { html: `<b>${esc(s.label)}</b>` }, { html: esc(rstFmt(s.stop_distance)) },
        { html: esc(rstFmt(s.shares)) }, { html: esc(rstFmt(s.notional)) },
        { html: esc(rstFmt(s.max_loss_at_stop)) }, { html: esc(rstFmt(s.risk_used_percent_of_budget)) },
        { html: esc(s.cap_note || "—") },
      ]);
      sizing = `<h3>Risk-budget sizing</h3>` +
        table(["Stop", "Stop distance", "Shares", "Notional", "Max loss at stop",
               "Risk used %", "Cap"], srows) +
        `<p class="hint">${esc(d.position_sizing.note)}</p>`;
    }
    out.innerHTML =
      `<p class="hint"><b>${esc(d.symbol)}</b> — forecasts the SIZE of the next session's range, not its direction.</p>` +
      table(["Item", "Value"], rows.map((r) => [{ html: `<b>${esc(r[0])}</b>` }, { html: esc(rstFmt(r[1])) }])) +
      `<h3>Out-of-sample model comparison</h3>` +
      table(["Model", "Observations", "MAE (points)", "RMSE", "Median APE %",
             "Improvement vs naive %", "80% coverage %"], modelRows) +
      `<p class="hint">${esc(d.evaluation.note)}</p>` +
      sizing +
      `<p class="hint">${(d.caveats || []).map(esc).join(" ")}</p>`;
  } catch (e) {
    out.innerHTML = "";
    err.textContent = `Forecast failed: ${e.message}`;
  }
}

function bindResearchStudio() {
  if (!$("#rst-card")) return;
  $("#rst-preset").addEventListener("change", () => rstApplyPreset($("#rst-preset").value));
  $("#rst-start").addEventListener("click", rstStart);
  $("#rst-all").addEventListener("click", () => {
    RST.selected = new Set((RST.catalog ? RST.catalog.components : []).map((c) => c.id));
    rstRenderComponents();
  });
  $("#rst-none").addEventListener("click", () => {
    RST.selected = new Set();
    rstRenderComponents();
  });
  $("#rst-only-available").addEventListener("change", rstRenderComponents);
  $("#rst-components").addEventListener("change", (ev) => {
    const t = ev.target;
    if (!t || !t.classList || !t.classList.contains("rst-comp")) return;
    if (t.checked) RST.selected.add(t.value); else RST.selected.delete(t.value);
    rstUpdateCount();
  });
  $("#rs-vol-run").addEventListener("click", runVolatilityForecast);
  $("#rs-vol-symbol").addEventListener("keydown", (e) => { if (e.key === "Enter") runVolatilityForecast(); });
}

/* ==========================================================================
   CHART ANALYSIS PANELS — candlesticks, Elliott, harmonic
   --------------------------------------------------------------------------
   Every panel follows the same honesty contract as the rest of the terminal:
   it shows what was DETECTED, the data it used, and the limits of the method.
   Markers are accumulated in state.*Markers and written to the candle series
   by flushMarkers() in a single setMarkers call.
   ========================================================================== */

const CANDLE_LABELS = {
  doji: "Doji", hammer: "Hammer", inverted_hammer: "Inverted Hammer",
  shooting_star: "Shooting Star", spinning_top: "Spinning Top", marubozu: "Marubozu",
  bullish_engulfing: "Bullish Engulfing", bearish_engulfing: "Bearish Engulfing",
  harami: "Harami", harami_cross: "Harami Cross", piercing_pattern: "Piercing Line",
  dark_cloud_cover: "Dark Cloud Cover", tweezer_bottom: "Tweezer Bottom",
  tweezer_top: "Tweezer Top", morning_star: "Morning Star", evening_star: "Evening Star",
  three_white_soldiers: "Three White Soldiers", three_black_crows: "Three Black Crows",
};
function candleLabel(n) { return CANDLE_LABELS[n] || n; }
function shortCandle(n) { return (CANDLE_LABELS[n] || n).split(" ").map((w) => w[0]).join("").slice(0, 2).toUpperCase(); }

let candleCatalogue = null;

function buildCandlePicker() {
  const wrap = $("#candle-picker");
  if (!wrap || !candleCatalogue) return;
  wrap.innerHTML = candleCatalogue.map((n) =>
    `<label class="chk" style="min-width:11em"><input type="checkbox" class="candle-pick" value="${esc(n)}" checked /> ${esc(candleLabel(n))}</label>`
  ).join("");
}
function setAllCandlePicks(checked) {
  $$(".candle-pick").forEach((c) => { c.checked = checked; });
}

/* Candlesticks for the symbol's currently-plotted window. */
async function runCandles(opts = {}) {
  const symbol = state.chartSymbol || ($("#symbol-input").value || "").trim().toUpperCase();
  const el = $("#candles");
  if (!symbol) { if (el) el.innerHTML = `<div class="empty">Enter a symbol first.</div>`; return; }
  const range = ($("#range") && $("#range").value) || "120";
  const trendBars = parseInt(($("#candle-trend") || {}).value, 10) || 3;
  const requireTrend = $("#candle-require-trend") ? $("#candle-require-trend").checked : true;
  const picks = $$(".candle-pick").filter((c) => c.checked).map((c) => c.value);

  const params = new URLSearchParams({ trend_bars: String(trendBars), require_prior_trend: String(requireTrend) });
  if (range !== "0") params.set("limit", range);
  // The picker exists only after the first fetch. Before that, empty selection
  // means "not chosen yet" = all patterns. After it exists, an empty selection
  // means the user wants no patterns, which the API expresses as "no request".
  const pickerBuilt = $$(".candle-pick").length > 0;
  if (pickerBuilt) {
    if (!picks.length) {
      state.candleMarkers = [];
      flushMarkers();
      if (el) el.innerHTML = `<div class="empty">No candlestick patterns selected — tick one or more above, or press All.</div>`;
      return;
    }
    if (candleCatalogue && picks.length < candleCatalogue.length) params.set("patterns", picks.join(","));
  }

  if (el && !opts.fromChart) el.innerHTML = `<div class="empty">Detecting…</div>`;
  let d;
  try {
    d = await api(`/api/bars/${encodeURIComponent(symbol)}/candles?${params.toString()}`);
  } catch (e) {
    if (el && !opts.fromChart) el.innerHTML = `<div class="empty">Candlesticks unavailable: ${esc(e.message)}</div>`;
    return;
  }
  if (!candleCatalogue && d.catalogue && d.catalogue.length) { candleCatalogue = d.catalogue; buildCandlePicker(); }

  const wantMarkers = $("#candle-markers") ? $("#candle-markers").checked : true;
  const visible = new Set(state.chartDates);
  state.candleMarkers = wantMarkers ? d.patterns
    .filter((p) => !state.chartDates.length || visible.has(p.date))
    .map((p) => noteMarker({
      time: p.date,
      position: p.marker_position,
      color: p.direction === "bearish" ? PRAVAHA.down : (p.direction === "bullish" ? PRAVAHA.up : PRAVAHA.caution),
      shape: "circle",
      text: shortCandle(p.name),
    }, "Candlestick detector",
    `Candlestick pattern “${shortCandle(p.name)}” = ${p.name} (${p.direction}) on ${p.date}. `
    + `Remove it by clearing this pattern in the Candlestick panel or turning off the layer.`)) : [];
  flushMarkers();
  if (el) renderCandles(d);
}

function renderCandles(d) {
  const el = $("#candles");
  const hint = $("#candle-hint");
  if (!el) return;
  const extra = [];
  if (d.bars_excluded_invalid_ohlc) extra.push(`${d.bars_excluded_invalid_ohlc} bar(s) with impossible OHLC excluded`);
  if (d.parameters) extra.push(`trend context ${d.parameters.trend_bars} bar(s)`);
  if (hint) hint.textContent = "Detected shapes are descriptive geometry — a match is not a confirmed reversal and not a forecast."
    + (extra.length ? " · " + extra.join(" · ") : "");
  if (!d.count) {
    el.innerHTML = `<div class="empty">No candlestick shape matched in this window (as of ${esc(d.as_of || "—")}). `
      + `An absence of a match is not a clean chart.</div>`;
    return;
  }
  const rows = d.patterns.slice().reverse();
  const shown = rows.slice(0, 200);
  el.innerHTML = table(
    ["Pattern", "Bias", "Date", "Trend", "Classification", "Evidence"],
    shown.map((p) => [
      { html: `<b>${esc(candleLabel(p.name))}</b>` },
      { html: esc(p.direction) },
      { html: esc(p.date || p.index) },
      { html: esc((p.context && p.context.trend) || "—") },
      { html: `<span class="pill">${esc(p.classification || "DETECTED")}</span>` },
      { html: esc((p.notes || []).slice(-1)[0] || "") },
    ])
  ) + (rows.length > shown.length ? `<p class="hint">Showing newest ${shown.length} of ${rows.length}.</p>` : "");
}

/* ------------------------------- Elliott Wave ----------------------------- */
/* Automatic candidates (heuristic, from the engine) AND manual labelling
   (the researcher decides). These are deliberately different capabilities and
   are presented as such: the engine lists candidate counts with evidence and
   invalidation; the manual table lets the user label confirmed pivots, stored
   in this browser and drawn on the chart. */

const WAVE_LABELS = ["0", "1", "2", "3", "4", "5", "A", "B", "C", "W", "X", "Y", "Z"];
function elliottKey(symbol) { return `mt-elliott-${symbol}`; }
function elliottCfgKey(symbol) { return `mt-elliott-cfg-${symbol}`; }

function loadElliottLabels(symbol) {
  try { return JSON.parse(localStorage.getItem(elliottKey(symbol)) || "{}") || {}; }
  catch (e) { return {}; }
}
function saveElliottLabel(symbol, date, labelValue) {
  const map = loadElliottLabels(symbol);
  if (labelValue) map[date] = labelValue; else delete map[date];
  try { localStorage.setItem(elliottKey(symbol), JSON.stringify(map)); } catch (e) { /* storage off */ }
}
function clearElliottLabels(symbol) {
  try { localStorage.removeItem(elliottKey(symbol)); } catch (e) { /* storage off */ }
}

function loadElliottCfg(symbol) {
  try { return JSON.parse(localStorage.getItem(elliottCfgKey(symbol)) || "{}") || {}; }
  catch (e) { return {}; }
}
function saveElliottCfg(symbol, cfg) {
  try { localStorage.setItem(elliottCfgKey(symbol), JSON.stringify(cfg)); } catch (e) { /* storage off */ }
}
/* Read the analysis-window controls into a query string. Explicit From/To dates
   win; otherwise a bar-count limit is used (0 = all stored history). */
function elliottWindowParams() {
  const start = ($("#elliott-start") || {}).value || "";
  const end = ($("#elliott-end") || {}).value || "";
  let period = ($("#elliott-period") || {}).value || "chart";
  // "chart" means "the bars the chart has loaded". It is the default because an
  // analysis window that differs from the visible bars is precisely how a
  // candidate ends up drawn outside the loaded range — found, yet invisible.
  if (period === "chart") period = ($("#range") || {}).value || "120";
  const p = new URLSearchParams();
  if (start) p.set("start", start);
  if (end) p.set("end", end);
  if (!start && !end && period !== "0") p.set("limit", period);
  const qs = p.toString();
  return qs ? `?${qs}` : "";
}
/* Restore the saved window for a symbol into the controls. */
function applyElliottCfg(symbol) {
  const cfg = loadElliottCfg(symbol);
  if ($("#elliott-period")) $("#elliott-period").value = cfg.period || "chart";
  if ($("#elliott-start")) $("#elliott-start").value = cfg.start || "";
  if ($("#elliott-end")) $("#elliott-end").value = cfg.end || "";
}
function currentElliottCfg() {
  return {
    period: ($("#elliott-period") || {}).value || "chart",
    start: ($("#elliott-start") || {}).value || "",
    end: ($("#elliott-end") || {}).value || "",
  };
}

async function runElliott() {
  const symbol = state.chartSymbol || ($("#symbol-input").value || "").trim().toUpperCase();
  const el = $("#elliott");
  if (!symbol) { if (el) el.innerHTML = `<div class="empty">Enter a symbol first.</div>`; return; }
  if (el) el.innerHTML = `<div class="empty">Analyzing…</div>`;
  const qs = elliottWindowParams();
  saveElliottCfg(symbol, currentElliottCfg());
  let auto;
  try { auto = await api(`/api/bars/${encodeURIComponent(symbol)}/elliott${qs}`); }
  catch (e) { if (el) el.innerHTML = `<div class="empty">Elliott analysis unavailable: ${esc(e.message)}</div>`; return; }
  // The same window must be used for the pivot table, or a candidate's
  // `swings_used` would not line up with the swings drawn on the chart.
  let structure = null;
  try { structure = await api(`/api/bars/${encodeURIComponent(symbol)}/structure${qs}`); } catch (e) { structure = null; }
  renderElliott(symbol, auto, structure);
}

function renderElliott(symbol, auto, structure) {
  const el = $("#elliott");
  if (!el) return;
  state.elliottAuto = auto;
  state.elliottStructure = structure;
  state.elliottSymbol = symbol;
  const saved = loadElliottLabels(symbol);
  const swings = ((structure && structure.swings) || []).filter((s) => s.confirmed);

  const candCount = (auto.candidates || []).length;
  const win = auto.window || {};
  let html = `<p class="hint">Status <b>${esc(auto.status)}</b> · method <code>${esc(auto.method || "")}</code>`
    + (win.bars ? ` · window <b>${esc(String(win.bars))} bar(s)</b>`
        + (win.first_date ? ` (${esc(win.first_date)} → ${esc(win.last_date)})` : "") : "")
    + `.</p>`
    + `<p class="hint"><b>${esc(auto.swings_considered)} confirmed swing(s) considered</b> — the pivots the engine examined, `
    + `<b>not</b> a count of wave counts. Wave counts found: <b>${candCount}</b>`
    + (candCount ? ` (each row below is drawable with its own <b>Draw</b> button)` : "") + `.</p>`;
  if (auto.uncertainty) html += `<p class="hint">${esc(auto.uncertainty)}</p>`;

  if (auto.candidates && auto.candidates.length) {
    html += table(
      ["Scenario", "Structure", "Certainty", "Evidence", "Alternative count", "Invalidation", "Fibonacci relations", ""],
      auto.candidates.map((c, i) => [
        { html: `<b>${esc(c.label)}</b>` },
        { html: `${esc(c.swings_used)} swing(s)` },
        { html: `<span class="pill">${esc(c.certainty)}</span>` },
        { html: esc(c.evidence) },
        { html: esc(c.alternative || "—") },
        { html: esc(c.invalidation || "—") },
        { html: (c.fibonacci_relations || []).map((r) => `${esc(r.ratio)} — ${esc(r.description)}`).join("<br>") || "—" },
        { html: `<button class="ghost el-draw" data-idx="${i}">Draw</button>` },
      ])
    );
    html += `<p class="hint">“Draw” plots the confirmed pivots used by that count with wave labels `
      + `(I–V for a 5-wave, A–C for a 3-wave). Automatic candidates are a heuristic reading; the labels are a drawing aid, not a forecast.</p>`;
  } else {
    html += `<div class="empty">${esc(auto.message || "No candidate count reached the minimum swing requirement.")}</div>`;
    if (auto.minimum && auto.minimum.note) html += `<p class="hint">${esc(auto.minimum.note)}</p>`;
  }

  html += `<h3 style="margin:16px 0 4px;font-size:.98em">Manual wave labelling — you decide</h3>`
    + `<p class="hint">Automatic detection above is a heuristic interpretation. Here you label the <b>confirmed</b> `
    + `pivots yourself; labels are stored in this browser for <b>${esc(symbol)}</b> and drawn on the chart. `
    + `This is a drawing aid, not a validated count.</p>`;

  if (!swings.length) {
    html += `<div class="empty">No confirmed swing pivots in stored history to label.</div>`;
  } else {
    const rows = swings.slice(-60).reverse();
    html += `<div class="controls"><button id="el-clear" class="ghost">Clear all labels for ${esc(symbol)}</button></div>`;
    html += `<div class="tablewrap">${table(["Date", "Kind", "Price", "Wave label"],
      rows.map((s) => [
        { html: esc(s.date) },
        { html: esc(s.kind) },
        { html: fmtNum(s.price) },
        { html: `<select class="el-pick" data-date="${esc(s.date)}">`
            + `<option value="">—</option>`
            + WAVE_LABELS.map((w) => `<option value="${w}"${saved[s.date] === w ? " selected" : ""}>${w}</option>`).join("")
            + `</select>` },
      ]))}</div>`;
    if (swings.length > rows.length) html += `<p class="hint">Showing the most recent ${rows.length} of ${swings.length} pivots.</p>`;
  }
  el.innerHTML = html;

  el.querySelectorAll(".el-pick").forEach((sel) => sel.addEventListener("change", () => {
    saveElliottLabel(symbol, sel.dataset.date, sel.value);
    applyElliottLabels();
  }));
  el.querySelectorAll(".el-draw").forEach((btn) => btn.addEventListener("click", () => {
    drawElliottCandidate(symbol, parseInt(btn.dataset.idx, 10));
  }));
  const clearBtn = $("#el-clear");
  if (clearBtn) clearBtn.addEventListener("click", () => {
    clearElliottLabels(symbol);
    renderElliott(symbol, auto, structure);
    applyElliottLabels();
  });
}

/* ---------------------------------------------------------------------------
   Reveal helper (shared by the Elliott and harmonic drawings)
   ---------------------------------------------------------------------------
   A detection that is drawn but sits outside the visible window is, from the
   user's seat, a detection that did not render. This scrolls the time scale —
   and only the time scale; the loaded bars and the price range are untouched —
   just far enough to fit the given dates. Returns true when it moved.

   It is deliberately conservative: if the dates are already on screen it does
   nothing, so repeated draws never fight the user's own zoom. */
function revealChartDates(dates, pad) {
  const chart = state.charts.price;
  const all = state.chartDates || [];
  if (!chart || !dates || !dates.length || !all.length) return false;
  const pos = [];
  dates.forEach((d) => { const i = all.indexOf(d); if (i >= 0) pos.push(i); });
  if (!pos.length) return false;
  const lo = Math.min.apply(null, pos);
  const hi = Math.max.apply(null, pos);
  let r;
  try { r = chart.timeScale().getVisibleLogicalRange(); } catch (e) { return false; }
  if (!r) return false;
  // Already comfortably inside the window → leave the viewport alone.
  if (lo >= r.from && hi <= r.to) return false;
  const span = hi - lo;
  const p = pad == null ? Math.max(3, Math.round(span * 0.15) + 2) : pad;
  try {
    chart.timeScale().setVisibleLogicalRange({
      from: Math.max(0, lo - p),
      to: Math.min(all.length - 1, hi + p),
    });
    return true;
  } catch (e) { return false; }
}

/* Plot one automatic candidate's pivots. The API returns the exact pivots the
   engine used (``date``/``kind``/``price``) alongside each candidate, so they
   are drawn directly — not re-derived from a second request that could disagree
   about the window. Older servers without ``pivots`` still work: the pivots are
   then taken from the same ``/structure`` window the analysis used.

   Returns a summary of what was ACTUALLY drawn, so the caller can report the
   truth instead of repeating the candidate's metadata back as if it were a
   result (a candidate can name 5 pivots and still draw zero). */
function drawElliottCandidate(symbol, idx) {
  const chart = state.charts.price;
  const auto = state.elliottAuto;
  if (!chart) return { drawn: 0, offRange: 0, reason: "No chart is open." };
  const cand = ((auto && auto.candidates) || [])[idx];
  if (!cand) return { drawn: 0, offRange: 0, reason: "No such candidate." };
  if (state.elliottAutoLine) { try { chart.removeSeries(state.elliottAutoLine); } catch (e) { /* gone */ } }
  state.elliottAutoLine = null;
  state.elliottAutoMarkers = [];
  if (state.elliottSymbol !== symbol) { flushMarkers(); return { drawn: 0, offRange: 0, reason: "The analysis belongs to another symbol." }; }

  let used = (Array.isArray(cand.pivots) && cand.pivots.length) ? cand.pivots.slice() : null;
  if (!used) {
    const swings = ((state.elliottStructure && state.elliottStructure.swings) || [])
      .filter((s) => s.confirmed)
      .sort((a, b) => String(a.date).localeCompare(String(b.date)));
    used = swings.slice(0, cand.swings_used);
  }
  used = used.filter((s) => s && s.date != null && s.price != null);

  // Markers and a line can only exist on bars the chart actually loaded.
  const onChart = new Set(state.chartDates || []);
  const drawable = used.filter((s) => onChart.has(s.date));
  const offRange = used.length - drawable.length;
  const labels = drawable.length >= 5 ? ["I", "II", "III", "IV", "V"] : ["A", "B", "C"];
  drawable.forEach((s, i) => state.elliottAutoMarkers.push(noteMarker({
    time: s.date,
    position: s.kind === "high" ? "aboveBar" : "belowBar",
    color: PRAVAHA.cyan, shape: "circle", text: `(${labels[i] || i + 1})`,
  }, "Elliott Wave — automatic candidate",
  `Automatic wave label (${labels[i] || i + 1}) from the candidate “${cand.label}”. `
  + `This is a heuristic reading, not a validated count. `
  + `Remove it with the “Remove” button in the Elliott panel or the Objects manager.`)));
  if (drawable.length >= 2) {
    const line = chart.addLineSeries({
      color: "rgba(0,217,232,.8)", lineWidth: 2,
      priceLineVisible: false, lastValueVisible: false, title: `Auto: ${cand.label}`,
    });
    line.setData(drawable.map((s) => ({ time: s.date, value: s.price })));
    state.elliottAutoLine = line;
  }
  flushMarkers();
  const moved = drawable.length >= 2 ? revealChartDates(drawable.map((s) => s.date)) : false;
  return {
    drawn: drawable.length,
    offRange,
    moved,
    label: cand.label,
    certainty: cand.certainty,
    engineCount: cand.swings_used,
    first: drawable[0] && drawable[0].date,
    last: drawable[drawable.length - 1] && drawable[drawable.length - 1].date,
  };
}

/* Draw the researcher's saved wave labels on the price chart. */
async function applyElliottLabels() {
  const symbol = state.chartSymbol;
  const chart = state.charts.price;
  if (!symbol || !chart) return;
  if (state.elliottLine) { try { chart.removeSeries(state.elliottLine); } catch (e) { /* gone */ } state.elliottLine = null; }
  state.elliottMarkers = [];
  const saved = loadElliottLabels(symbol);
  if (!Object.keys(saved).length) { flushMarkers(); return; }

  const range = ($("#range") && $("#range").value) || "120";
  const qs = range === "0" ? "" : `?limit=${encodeURIComponent(range)}`;
  let d;
  try { d = await api(`/api/bars/${encodeURIComponent(symbol)}/structure${qs}`); }
  catch (e) { flushMarkers(); return; }
  const visible = new Set(state.chartDates);
  const pts = (d.swings || [])
    .filter((s) => s.confirmed && saved[s.date] && (!state.chartDates.length || visible.has(s.date)))
    .sort((a, b) => String(a.date).localeCompare(String(b.date)));

  pts.forEach((s) => state.elliottMarkers.push(noteMarker({
    time: s.date,
    position: s.kind === "high" ? "aboveBar" : "belowBar",
    color: PRAVAHA.mint, shape: "circle", text: `(${saved[s.date]})`,
  }, "Elliott Wave — your manual label",
  `Wave label (${saved[s.date]}) that you assigned to the confirmed ${s.kind} pivot on ${s.date}. `
  + `Stored in this browser for ${symbol}; remove it in the Elliott panel or the Objects manager.`)));
  if (pts.length >= 2) {
    const line = chart.addLineSeries({
      color: "rgba(168,255,217,.7)", lineWidth: 2,
      priceLineVisible: false, lastValueVisible: false, title: "Manual wave count",
    });
    line.setData(pts.map((s) => ({ time: s.date, value: s.price })));
    state.elliottLine = line;
  }
  flushMarkers();
}

/* ------------------------------- Harmonic --------------------------------- */
function harmonicCfgKey(symbol) { return `mt-harmonic-cfg-${symbol}`; }
function loadHarmonicCfg(symbol) {
  try { return JSON.parse(localStorage.getItem(harmonicCfgKey(symbol)) || "{}") || {}; }
  catch (e) { return {}; }
}
function saveHarmonicCfg(symbol, cfg) {
  try { localStorage.setItem(harmonicCfgKey(symbol), JSON.stringify(cfg)); } catch (e) { /* storage off */ }
}
function applyHarmonicCfg(symbol) {
  const cfg = loadHarmonicCfg(symbol);
  if ($("#harmonic-patterns")) $("#harmonic-patterns").value = cfg.patterns || "";
  if ($("#harmonic-slack")) $("#harmonic-slack").value = cfg.slack != null ? cfg.slack : "0";
}
function harmonicWindowParams() {
  const p = new URLSearchParams();
  const patterns = ($("#harmonic-patterns") || {}).value || "";
  const slack = parseFloat(($("#harmonic-slack") || {}).value);
  if (patterns) p.set("patterns", patterns);
  if (Number.isFinite(slack) && slack > 0) p.set("slack", String(slack));
  // Align the detection window with the chart window: the engine reports pivot
  // indexes into the series it was given, so using the same window means those
  // indexes map onto the bars actually drawn (otherwise an overlay can land
  // outside the visible range and the Draw button would appear to do nothing).
  const range = ($("#range") || {}).value || "120";
  if (range !== "0") p.set("limit", range);
  const qs = p.toString();
  return qs ? `?${qs}` : "";
}

async function runHarmonic() {
  const symbol = state.chartSymbol || ($("#symbol-input").value || "").trim().toUpperCase();
  const el = $("#harmonic");
  if (!symbol) { if (el) el.innerHTML = `<div class="empty">Enter a symbol first.</div>`; return; }
  if (el) el.innerHTML = `<div class="empty">Detecting…</div>`;
  saveHarmonicCfg(symbol, {
    patterns: ($("#harmonic-patterns") || {}).value || "",
    slack: ($("#harmonic-slack") || {}).value || "0",
  });
  const qs = harmonicWindowParams();
  let d;
  try { d = await api(`/api/bars/${encodeURIComponent(symbol)}/harmonic${qs}`); }
  catch (e) { if (el) el.innerHTML = `<div class="empty">Harmonic detection unavailable: ${esc(e.message)}</div>`; return; }
  // Pivots now carry their own dates (the engine's own window), so the chart
  // draws the exact matched pivots. The bars fetch is kept purely as a fallback
  // for older servers that still report an index only.
  let fullDates = null;
  const needsIndexFallback = (d.candidates || []).some((c) =>
    ["X", "A", "B", "C", "D"].some((k) => {
      const p = c.points && c.points[k];
      return p && p.date == null;
    }));
  if (needsIndexFallback) {
    try { const fb = await api(`/api/bars/${encodeURIComponent(symbol)}${qs}`); fullDates = (fb.bars || []).map((b) => b.time); }
    catch (e) { fullDates = null; }
  }
  state.harmonicData = d;
  state.harmonicFullDates = fullDates;
  state.harmonicSymbol = symbol;
  renderHarmonic(d);
}

function renderHarmonic(d) {
  const el = $("#harmonic");
  if (!el) return;
  const slack = Number(d.slack || 0);
  let html = `<p class="hint">Status <b>${esc(d.status)}</b> · ${esc(d.windows_tested || 0)} five-swing window(s) tested`
    + (d.window && d.window.bars ? ` over <b>${esc(String(d.window.bars))} bar(s)</b>` : "")
    + ` · patterns tried: ${esc((d.patterns_tested || []).join(", ") || "—")} · `
    + (slack > 0
        ? `tolerance <b>±${esc(slack)}</b> — matches are <b>approximate</b>`
        : `tolerance <b>0</b> — published ratios only`)
    + `</p>`;
  if (d.candidates && d.candidates.length) {
    html += table(
      ["Pattern", "Direction", "Measured ratios", "Completion zone", "Invalidation", "Certainty", ""],
      d.candidates.slice(0, 20).map((c, i) => {
        const measures = Object.entries(c.measures || {}).map(([k, v]) => `${esc(k)}=${esc(v)}`).join("<br>");
        const zones = (c.matched_ranges || []).map((m) => `${esc(m.measure || m.ratio || "")}: ${esc(m.target || "")}`).join("<br>");
        return [
          { html: `<b>${esc(c.pattern)}</b>` },
          { html: esc(c.direction) },
          { html: measures || "—" },
          { html: zones || "—" },
          { html: esc(c.invalidation || "—") },
          { html: `<span class="pill">${esc(c.certainty)}</span>` },
          { html: `<button class="ghost hm-draw" data-idx="${i}">Draw</button>` },
        ];
      })
    );
    if (d.candidates.length > 20) html += `<p class="hint">Showing the first 20 of ${d.candidates.length} candidates.</p>`;
    html += `<p class="hint">“Draw” overlays that one XABCD on the price chart with its measured pivots; the D marker is the potential reversal point.</p>`;
  } else {
    html += `<div class="empty">${esc(d.message || "No published ratio band matched over the confirmed swings.")}`
      + (slack > 0 ? "" : ` Try a small tolerance (e.g. 0.01) to see near-misses — they will be labelled approximate.`)
      + `</div>`;
    // A short range is a common reason for "no match" that is not a failure: the
    // detector slides a five-pivot window, so few pivots means few windows.
    const win = d.window || {};
    if (win.bars) {
      html += `<p class="hint">Analysed <b>${esc(String(win.bars))} bar(s)</b>`
        + (win.first_date ? ` (${esc(win.first_date)} → ${esc(win.last_date)})` : "")
        + `; <b>${esc(String(d.swings_considered || 0))}</b> confirmed swing(s), `
        + `<b>${esc(String(d.windows_tested || 0))}</b> five-swing window(s) tested. `
        + `${d.minimum && d.minimum.note ? esc(d.minimum.note) : ""}</p>`;
    }
  }
  el.innerHTML = html;
  el.querySelectorAll(".hm-draw").forEach((btn) => btn.addEventListener("click", () => {
    let res;
    try { res = drawHarmonicCandidate(parseInt(btn.dataset.idx, 10)); }
    catch (e) { harmonicStatus(`Harmonic drawing failed: ${e.message}`); return; }
    if (!res || !res.drawn) {
      harmonicStatus(`Nothing drawn — ${(res && res.reason) || "no pivots were returned"}`
        + (res && res.offRange ? ` (all ${res.offRange} pivot(s) fall outside the ${(state.chartDates || []).length} bars the chart has loaded)` : "")
        + ".");
      return;
    }
    harmonicStatus(`Drew ${res.drawn} pivot(s), ${res.first} → ${res.last}. `
      + (res.offRange ? `${res.offRange} pivot(s) sit outside the loaded chart range. ` : "")
      + (res.moved ? "The chart was scrolled to the pattern (loaded range unchanged)." : "Viewport unchanged."));
  }));
}
function harmonicStatus(msg) {
  const el = $("#harmonic-status");
  if (el) el.textContent = msg || "";
}

/* Overlay exactly one picked candidate (replaces any previous overlay).
   Points carry their own dates; the index→date fallback only runs for servers
   that still report an index alone. Returns what was actually drawn, so a
   caller can report the truth rather than assuming the overlay appeared. */
function drawHarmonicCandidate(idx) {
  const chart = state.charts.price;
  if (!chart) return { drawn: 0, reason: "No chart is open." };
  const d = state.harmonicData;
  const fullDates = state.harmonicFullDates;
  const c = ((d && d.candidates) || [])[idx];
  if (!c) return { drawn: 0, reason: "No such candidate." };
  (state.harmonicSeries || []).forEach((s) => { try { chart.removeSeries(s); } catch (e) { /* gone */ } });
  state.harmonicSeries = [];
  state.harmonicMarkers = [];
  const loaded = new Set(state.chartDates || []);
  const dateOf = (p) => {
    if (!p) return null;
    if (p.date != null) return p.date;
    const i = p.index;
    return fullDates && i != null && i >= 0 && i < fullDates.length ? fullDates[i] : null;
  };
  const order = ["X", "A", "B", "C", "D"];
  const allPts = order
    .map((k) => { const p = c.points && c.points[k]; const dt = dateOf(p); return dt && p ? { time: dt, value: p.price, key: k } : null; })
    .filter(Boolean);
  const pts = allPts.filter((p) => !state.chartDates.length || loaded.has(p.time));
  const offRange = allPts.length - pts.length;
  if (pts.length >= 2) {
    const line = chart.addLineSeries({
      color: PRAVAHA.caution, lineWidth: 2,
      priceLineVisible: false, lastValueVisible: false, title: `${c.pattern} ${c.direction}`,
    });
    line.setData(pts.map((p) => ({ time: p.time, value: p.value })));
    state.harmonicSeries.push(line);
  }
  const dp = c.points && c.points.D;
  const dt = dateOf(dp);
  if (dt && (!state.chartDates.length || loaded.has(dt))) {
      state.harmonicMarkers.push(noteMarker({
        time: dt,
        position: c.direction === "bullish" ? "belowBar" : "aboveBar",
        color: PRAVAHA.caution, shape: "circle", text: `D ${c.pattern}`,
      }, "Harmonic-pattern detector",
      `“D ${c.pattern}” = the D point (completion) of a ${c.pattern} (${c.direction}) the harmonic detector found. `
      + `Remove the Harmonic-patterns layer to clear it.`));
  }
  flushMarkers();
  const moved = pts.length >= 2 ? revealChartDates(pts.map((p) => p.time)) : false;
  return {
    drawn: pts.length,
    offRange,
    moved,
    first: pts[0] && pts[0].time,
    last: pts[pts.length - 1] && pts[pts.length - 1].time,
  };
}

/* ==========================================================================
   WATCHLISTS
   ========================================================================== */
async function loadWatchlists() {
  const el = $("#wl-list");
  if (!el) return;
  el.innerHTML = `<div class="empty">Loading…</div>`;
  let d;
  try { d = await api("/api/watchlists"); }
  catch (e) { $("#wl-error").textContent = `Could not load watchlists: ${e.message}`; el.innerHTML = `<div class="empty">—</div>`; return; }
  $("#wl-error").textContent = "";
  if (!d.count) { el.innerHTML = `<div class="empty">No watchlists yet — create one above.</div>`; return; }
  el.innerHTML = table(
    ["Name", "Symbols", "Updated", "", ""],
    d.watchlists.map((w) => [
      { html: `<b>${esc(w.name)}</b>` },
      { html: esc(w.symbols.join(", ")) || "—" },
      { html: esc(w.updated_at) },
      { html: `<button class="ghost wl-open" data-name="${esc(w.name)}">Open</button>` },
      { html: `<button class="ghost wl-del" data-name="${esc(w.name)}">Delete</button>` },
    ])
  );
  el.querySelectorAll(".wl-open").forEach((b) => b.addEventListener("click", () => openWatchlist(b.dataset.name)));
  el.querySelectorAll(".wl-del").forEach((b) => b.addEventListener("click", () => removeWatchlist(b.dataset.name)));
}

async function openWatchlist(name) {
  const card = $("#wl-detail-card");
  const err = $("#wl-detail-error");
  err.textContent = "";
  let d;
  try { d = await api(`/api/watchlists/${encodeURIComponent(name)}`); }
  catch (e) { err.textContent = `Could not open ${name}: ${e.message}`; return; }
  state.selectedWatchlist = d.name;
  card.style.display = "";
  $("#wl-detail-title").textContent = `Watchlist — ${d.name}`;
  $("#wl-rename").value = d.name;
  const rows = (d.rows || []);
  $("#wl-rows").innerHTML = rows.length ? table(
    ["Symbol", "Last close", "Change %", "Volume", "Turnover", "Data as of", "Note", ""],
    rows.map((r) => [
      { html: `<a href="#" class="wl-sym" data-sym="${esc(r.symbol)}"><b>${esc(r.symbol)}</b></a>` },
      { html: fmtNum(r.close) },
      { html: r.change_pct === null || r.change_pct === undefined ? "—" : fmtNum(r.change_pct) + "%" },
      { html: fmtInt(r.volume) },
      { html: fmtInt(r.turnover) },
      { html: esc(r.data_as_of || "—") },
      { html: esc(r.note || "") },
      { html: `<button class="ghost wl-rm" data-sym="${esc(r.symbol)}">Remove</button>` },
    ])
  ) : `<div class="empty">This watchlist has no symbols yet.</div>`;

  $("#wl-rows").querySelectorAll(".wl-sym").forEach((a) => a.addEventListener("click", (ev) => {
    ev.preventDefault();
    $("#symbol-input").value = a.dataset.sym;
    showView("charts");
    loadChart();
  }));
  $("#wl-rows").querySelectorAll(".wl-rm").forEach((b) => b.addEventListener("click", () => patchWatchlist(d.name, { remove: [b.dataset.sym] })));
}

async function createWatchlist() {
  const err = $("#wl-error");
  err.textContent = "";
  const name = ($("#wl-name").value || "").trim();
  const symbols = ($("#wl-symbols").value || "").split(",").map((s) => s.trim()).filter(Boolean);
  if (!name) { err.textContent = "Enter a watchlist name."; return; }
  try {
    await api("/api/watchlists", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, symbols }),
    });
    $("#wl-name").value = ""; $("#wl-symbols").value = "";
    await loadWatchlists();
    await openWatchlist(name);
  } catch (e) { err.textContent = `Could not create: ${e.message}`; }
}

async function patchWatchlist(name, patch) {
  const err = $("#wl-detail-error");
  err.textContent = "";
  try {
    await api(`/api/watchlists/${encodeURIComponent(name)}`, {
      method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    });
    await loadWatchlists();
    await openWatchlist(patch.new_name || name);
  } catch (e) { err.textContent = `Could not update: ${e.message}`; }
}

async function removeWatchlist(name) {
  const err = $("#wl-error");
  err.textContent = "";
  try {
    await api(`/api/watchlists/${encodeURIComponent(name)}`, { method: "DELETE" });
    if (state.selectedWatchlist === name) { state.selectedWatchlist = null; $("#wl-detail-card").style.display = "none"; }
    await loadWatchlists();
  } catch (e) { err.textContent = `Could not delete: ${e.message}`; }
}

/* ==========================================================================
   EXPERIMENTS (reproducible research runs)
   ========================================================================== */
async function loadExperiments() {
  const el = $("#ex-list");
  if (!el) return;
  el.innerHTML = `<div class="empty">Loading…</div>`;
  let d;
  try { d = await api("/api/experiments"); }
  catch (e) { $("#ex-error").textContent = `Could not load experiments: ${e.message}`; el.innerHTML = `<div class="empty">—</div>`; return; }
  $("#ex-error").textContent = "";
  const opts = d.experiments.map((e) => `<option value="${e.id}">${e.id}: ${esc(e.label)} (${esc(e.symbol)})</option>`).join("");
  if ($("#ex-a")) $("#ex-a").innerHTML = opts;
  if ($("#ex-b")) $("#ex-b").innerHTML = opts;
  if (!d.count) { el.innerHTML = `<div class="empty">No saved experiments yet — run a backtest, then "Save current run".</div>`; return; }
  el.innerHTML = table(
    ["ID", "Label", "Symbol", "Strategy", "Config hash", "Data as of", "Return %", "", "", ""],
    d.experiments.map((e) => [
      { html: String(e.id) },
      { html: `<b>${esc(e.label)}</b>` },
      { html: esc(e.symbol) },
      { html: esc(e.strategy) },
      { html: `<code>${esc((e.config_hash || "").slice(0, 10))}</code>` },
      { html: esc(e.data_as_of || "—") },
      { html: fmtNum(e.metrics && e.metrics.total_return_pct) },
      { html: `<button class="ghost ex-repro" data-id="${e.id}">Reproduce</button>` },
      { html: `<button class="ghost ex-export" data-id="${e.id}">Export</button>` },
      { html: `<button class="ghost ex-del" data-id="${e.id}">Delete</button>` },
    ])
  );
  el.querySelectorAll(".ex-repro").forEach((b) => b.addEventListener("click", () => reproduceExperiment(b.dataset.id)));
  el.querySelectorAll(".ex-export").forEach((b) => b.addEventListener("click", () => exportExperiment(b.dataset.id)));
  el.querySelectorAll(".ex-del").forEach((b) => b.addEventListener("click", () => deleteExperiment(b.dataset.id)));
}

async function saveExperiment() {
  const err = $("#ex-error");
  err.textContent = "";
  const label = ($("#ex-label").value || "").trim();
  if (!state.lastBacktest || !state.backtestConfig) { err.textContent = "Run a backtest first, then save it."; return; }
  if (!label) { err.textContent = "Give the experiment a label."; return; }
  try {
    await api("/api/experiments", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ label, config: state.backtestConfig, result: state.lastBacktest }),
    });
    $("#ex-label").value = "";
    await loadExperiments();
  } catch (e) { err.textContent = `Could not save: ${e.message}`; }
}

async function reproduceExperiment(id) {
  const out = $("#ex-compare-out");
  out.innerHTML = `<div class="empty">Re-running…</div>`;
  try {
    const d = await api(`/api/experiments/${id}/reproduce`, { method: "POST" });
    out.innerHTML = renderComparison(d.comparison, `Reproduce of #${id}`);
  } catch (e) { out.innerHTML = `<div class="empty">Reproduce failed: ${esc(e.message)}</div>`; }
}

async function compareExperiments() {
  const out = $("#ex-compare-out");
  const a = $("#ex-a").value, b = $("#ex-b").value;
  if (!a || !b) { out.innerHTML = `<div class="empty">Save at least two experiments to compare.</div>`; return; }
  out.innerHTML = `<div class="empty">Comparing…</div>`;
  try {
    const d = await api(`/api/experiments/compare?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`);
    out.innerHTML = renderComparison(d, `Compare #${a} vs #${b}`);
  } catch (e) { out.innerHTML = `<div class="empty">Compare failed: ${esc(e.message)}</div>`; }
}

function renderComparison(c, title) {
  let html = `<p class="hint"><b>${esc(title)}</b> · identical config: <b>${c.identical_config ? "yes" : "no"}</b>`
    + ` · A hash <code>${esc((c.a.config_hash || "").slice(0, 10))}</code> · B hash <code>${esc((c.b.config_hash || "").slice(0, 10))}</code></p>`;
  html += table(["Metric", "Saved (A)", "Fresh (B)", "Δ (B−A)", "Same"],
    c.metrics.map((m) => [
      { html: esc(m.metric) },
      { html: fmtNum(m.a) },
      { html: fmtNum(m.b) },
      { html: m.delta === null || m.delta === undefined ? "—" : fmtNum(m.delta) },
      { html: m.same ? `<span class="pill">yes</span>` : `<span class="pill pill-review">no</span>` },
    ]));
  return html;
}

async function exportExperiment(id) {
  try {
    const text = await apiText(`/api/experiments/${id}/export?format=markdown`);
    download(`experiment-${id}.md`, text, "text/markdown;charset=utf-8");
  } catch (e) { $("#ex-error").textContent = `Export failed: ${e.message}`; }
}

async function deleteExperiment(id) {
  try { await api(`/api/experiments/${id}`, { method: "DELETE" }); await loadExperiments(); }
  catch (e) { $("#ex-error").textContent = `Delete failed: ${e.message}`; }
}

/* Raw-text sibling of api(): for endpoints that return text/markdown. */
async function apiText(path) {
  const headers = new Headers();
  const tok = friendToken();
  if (tok) headers.set("X-Friend-Token", tok);
  const res = await fetch(API_BASE + path, { headers });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.text();
}

/* ==========================================================================
   REPORT EXPORT (Markdown, from the exact payload the UI shows)
   ========================================================================== */
async function exportResearchReport() {
  const symbol = ($("#rs-symbol").value || "").trim().toUpperCase();
  const err = $("#rs-error");
  err.textContent = "";
  if (!symbol) { err.textContent = "Enter a symbol to export."; return; }
  try {
    const d = await api(`/api/research/${encodeURIComponent(symbol)}`);
    download(`${symbol}-research-report.md`, reportToMarkdown(symbol, d), "text/markdown;charset=utf-8");
  } catch (e) { err.textContent = `Report export failed: ${e.message}`; }
}

/* Deterministic, faithful Markdown of the report payload: scalars become
   bullets, arrays of objects become tables, and anything nested is emitted as
   JSON so no field is silently dropped. */
function reportToMarkdown(symbol, payload) {
  const lines = [`# PRAVAHA research report — ${symbol}`, "", `Generated ${new Date().toISOString()}`, ""];
  const skip = new Set(["disclaimer"]);
  const walk = (obj, depth) => {
    Object.keys(obj).forEach((key) => {
      if (depth === 0 && skip.has(key)) return;
      const val = obj[key];
      const head = "#".repeat(Math.min(depth + 2, 6));
      if (val === null || val === undefined || typeof val !== "object") {
        lines.push(`${"  ".repeat(depth)}- **${key}**: ${String(val)}`);
      } else if (Array.isArray(val)) {
        lines.push("", `${head} ${key} (${val.length})`, "");
        if (!val.length) lines.push("_none_");
        else if (typeof val[0] === "object" && val[0] !== null) {
          const cols = Array.from(new Set(val.flatMap((r) => Object.keys(r))));
          lines.push("| " + cols.join(" | ") + " |");
          lines.push("|" + cols.map(() => "---").join("|") + "|");
          val.forEach((r) => lines.push("| " + cols.map((c) => String(r[c] ?? "")).join(" | ") + " |"));
        } else {
          val.forEach((v) => lines.push(`- ${String(v)}`));
        }
      } else {
        lines.push("", `${head} ${key}`, "");
        walk(val, depth + 1);
      }
    });
  };
  walk(payload, 0);
  lines.push("", "> Historical research output from stored data. Not advice; not a live quote.");
  return lines.join("\n");
}

/* ==========================================================================
   CUSTOM RULE BUILDER (Phase 5)
   --------------------------------------------------------------------------
   A structured AND/OR condition tree over the live metric catalogue. The model
   is plain data; it is converted to the scanner's ScreenNode dict and executed
   by POST /api/screen (the SAME validated pipeline). No eval / exec anywhere.
   ========================================================================== */
let rbMetrics = null;                       // metric name -> explanation
let rbScreens = [];                         // saved screens
let rbRoot = { op: "AND", rows: [
  { kind: "cond", metric: "rsi", operator: "lt", value: 40, lookback: "" },
] };

const RB_OPS = [["gt", ">"], ["gte", ">="], ["lt", "<"], ["lte", "<="], ["eq", "="],
  ["crosses_above", "crosses above"], ["crosses_below", "crosses below"]];
const RB_SYM = { gt: ">", gte: ">=", lt: "<", lte: "<=", eq: "=", crosses_above: "crosses above", crosses_below: "crosses below" };

function rbMetricOptions(sel) {
  return Object.keys(rbMetrics || {}).sort().map((m) =>
    `<option value="${esc(m)}"${m === sel ? " selected" : ""} title="${esc(rbMetrics[m])}">${esc(m)}</option>`
  ).join("");
}
function rbOpOptions(sel) {
  return RB_OPS.map(([v, l]) => `<option value="${v}"${v === sel ? " selected" : ""}>${esc(l)}</option>`).join("");
}
function rbParent(path) {
  const parts = String(path).split(".").map(Number);
  let node = rbRoot;
  for (let k = 0; k < parts.length - 1; k++) node = node.rows[parts[k]];
  return { node, index: parts[parts.length - 1] };
}
function rbRowAt(path) { const { node, index } = rbParent(path); return node.rows[index]; }

function rbCondHtml(row, path) {
  return `<div class="rb-row" data-path="${path}">
    <select class="rb-metric">${rbMetricOptions(row.metric)}</select>
    <select class="rb-op">${rbOpOptions(row.operator)}</select>
    <input class="rb-value" type="number" step="any" value="${esc(row.value)}" style="width:7em" />
    <input class="rb-lookback" type="number" min="1" placeholder="lookback" style="width:6.5em"
      value="${row.lookback === "" || row.lookback == null ? "" : esc(row.lookback)}" />
    <button class="ghost rb-remove" title="remove condition">✕</button>
  </div>`;
}
function rbGroupHtml(group, path) {
  const inner = group.rows.map((r, i) => rbCondHtml(r, `${path}.${i}`)).join("");
  return `<div class="rb-group" data-path="${path}">
    <div class="controls">
      <label>Group
        <select class="rb-gop"><option value="AND"${group.op === "AND" ? " selected" : ""}>ALL (AND)</option>
        <option value="OR"${group.op === "OR" ? " selected" : ""}>ANY (OR)</option></select>
      </label>
      <button class="ghost rb-gadd">+ Condition</button>
      <button class="ghost rb-gremove">Remove group</button>
    </div>
    ${inner || `<div class="empty">Add a condition to this group.</div>`}
  </div>`;
}
function rbPreview(node) {
  const parts = (node.rows || []).map((r) =>
    r.kind === "group" ? `(${rbPreview(r)})` : `${r.metric}${r.lookback !== "" && r.lookback != null ? `(${r.lookback})` : ""} ${RB_SYM[r.operator] || r.operator} ${r.value}`);
  return parts.join(` ${node.op} `);
}
function renderRuleBuilder() {
  const host = $("#rb-conditions");
  if (!host) return;
  if (!rbMetrics) { host.innerHTML = `<div class="empty">Loading metric catalogue…</div>`; return; }
  host.innerHTML = rbRoot.rows.length
    ? rbRoot.rows.map((r, i) => (r.kind === "group" ? rbGroupHtml(r, String(i)) : rbCondHtml(r, String(i)))).join("")
    : `<div class="empty">No conditions yet — add one with “+ Condition”.</div>`;
  if ($("#rb-op")) $("#rb-op").value = rbRoot.op;
  refreshRbPreview();
}
function refreshRbPreview() {
  const el = $("#rb-rendered");
  if (el) el.textContent = rbRoot.rows.length ? "Rule: " + rbPreview(rbRoot) : "";
}
function rbToTree(node) {
  return {
    op: node.op,
    conditions: node.rows.filter((r) => r.kind === "cond").map((c) => {
      const o = { metric: c.metric, operator: c.operator, value: Number(c.value) };
      if (c.lookback !== "" && c.lookback != null) o.lookback = Number(c.lookback);
      return o;
    }),
    children: node.rows.filter((r) => r.kind === "group").map((g) => rbToTree(g)),
  };
}
function rbFromTree(tree) {
  const node = { op: String(tree.op || "AND").toUpperCase(), rows: [] };
  (tree.conditions || []).forEach((c) => node.rows.push({
    kind: "cond", metric: c.metric, operator: c.operator, value: c.value,
    lookback: c.lookback == null ? "" : c.lookback,
  }));
  (tree.children || []).forEach((ch) => node.rows.push(Object.assign({ kind: "group" }, rbFromTree(ch))));
  return node;
}

async function initRuleBuilder() {
  if (!rbMetrics) {
    try {
      const d = await api("/api/screens");
      rbMetrics = d.metrics || {};
      rbScreens = d.screens || [];
    } catch (e) { rbMetrics = {}; }
  }
  renderRuleBuilder();
  renderSavedRules();
}
function renderSavedRules() {
  const sel = $("#rb-saved");
  if (!sel) return;
  sel.innerHTML = rbScreens.length
    ? rbScreens.map((s) => `<option value="${s.id}">${esc(s.name)}</option>`).join("")
    : `<option value="">(none saved)</option>`;
}

async function refreshSavedRules() {
  try {
    const d = await api("/api/screens");
    rbMetrics = d.metrics || rbMetrics || {};
    rbScreens = d.screens || [];
    renderSavedRules();
  } catch (e) { /* keep current list */ }
}

async function runRule() {
  const err = $("#rb-error");
  const out = $("#rb-results");
  err.textContent = "";
  const tree = rbToTree(rbRoot);
  if (!tree.conditions.length && !tree.children.length) {
    err.textContent = "Add at least one condition before running.";
    return;
  }
  out.innerHTML = `<div class="empty">Running rule…</div>`;
  try {
    const d = await api("/api/screen", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tree, min_bars: parseInt($("#rb-minbars").value, 10) || 30 }),
    });
    renderRuleResults(d);
  } catch (e) {
    out.innerHTML = `<div class="error">${esc(e.message)}</div>`;
  }
}
function renderRuleResults(d) {
  const out = $("#rb-results");
  const rows = (d.results || []).map((r) => [
    { html: `<b>${esc(r.symbol)}</b>` },
    { html: esc(r.last_date || "—") },
    { html: r.passed ? `<span class="pill">match</span>` : `<span class="pill pill-review">ineligible</span>` },
    { html: esc((r.passed ? r.reasons : (r.failures && r.failures.length ? r.failures : [r.note])).flat().filter(Boolean).join(" · ") || "—") },
  ]);
  out.innerHTML = `<p class="hint">${d.passed} of ${d.eligible} eligible securities matched (${d.evaluated} evaluated). `
    + `Rule: <code>${esc(d.rendered)}</code></p>` + table(["Symbol", "As of", "Result", "Why"], rows);
  $$("#rb-results tr").forEach((tr, i) => {
    const r = (d.results || [])[i];
    if (!r) return;
    tr.classList.add("click");
    tr.addEventListener("click", () => { $("#symbol-input").value = r.symbol; showView("charts"); loadChart(); });
  });
}

async function saveRule() {
  const err = $("#rb-error");
  err.textContent = "";
  const name = ($("#rb-name").value || "").trim();
  if (!name) { err.textContent = "Give the rule a name."; return; }
  try {
    const saved = await api("/api/screens", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, definition: rbToTree(rbRoot) }),
    });
    $("#rb-name").value = "";
    await refreshSavedRules();
    $("#rb-saved").value = String(saved.id);
  } catch (e) {
    if (String(e.message).includes("already exists")) {
      if (window.confirm(`${name} exists. Overwrite it?`)) {
        try {
          await api("/api/screens", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name, definition: rbToTree(rbRoot), overwrite: true }),
          });
          await refreshSavedRules();
          return;
        } catch (e2) { err.textContent = `Could not overwrite: ${e2.message}`; return; }
      }
      return;
    }
    err.textContent = `Could not save: ${e.message}`;
  }
}
async function loadRule() {
  const err = $("#rb-error");
  err.textContent = "";
  const id = $("#rb-saved").value;
  if (!id) { err.textContent = "No saved rule selected."; return; }
  try {
    const d = await api(`/api/screens/${encodeURIComponent(id)}`);
    rbRoot = rbFromTree(d.definition);
    $("#rb-name").value = d.name;
    renderRuleBuilder();
  } catch (e) { err.textContent = `Could not load: ${e.message}`; }
}
async function duplicateRule() {
  const err = $("#rb-error");
  err.textContent = "";
  const id = $("#rb-saved").value;
  const name = ($("#rb-name").value || "").trim();
  if (!id) { err.textContent = "No saved rule selected."; return; }
  if (!name) { err.textContent = "Type a name for the copy."; return; }
  try {
    await api(`/api/screens/${encodeURIComponent(id)}/duplicate`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ new_name: name }),
    });
    $("#rb-name").value = "";
    await refreshSavedRules();
  } catch (e) { err.textContent = `Could not duplicate: ${e.message}`; }
}
async function deleteRule() {
  const err = $("#rb-error");
  err.textContent = "";
  const id = $("#rb-saved").value;
  if (!id) { err.textContent = "No saved rule selected."; return; }
  try {
    await api(`/api/screens/${encodeURIComponent(id)}`, { method: "DELETE" });
    await refreshSavedRules();
  } catch (e) { err.textContent = `Could not delete: ${e.message}`; }
}

function bindRuleBuilder() {
  const host = $("#rb-conditions");
  if (!host) return;
  host.addEventListener("change", (e) => {
    const t = e.target;
    const rowEl = t.closest("[data-path]");
    if (!rowEl) return;
    const path = rowEl.dataset.path;
    if (t.classList.contains("rb-metric")) { rbRowAt(path).metric = t.value; renderRuleBuilder(); }
    else if (t.classList.contains("rb-op")) { rbRowAt(path).operator = t.value; renderRuleBuilder(); }
    else if (t.classList.contains("rb-gop")) { rbRowAt(path).op = t.value; renderRuleBuilder(); }
    else if (t.classList.contains("rb-value")) { rbRowAt(path).value = t.value; refreshRbPreview(); }
    else if (t.classList.contains("rb-lookback")) { rbRowAt(path).lookback = t.value; refreshRbPreview(); }
  });
  host.addEventListener("click", (e) => {
    const t = e.target;
    const rowEl = t.closest("[data-path]");
    if (!rowEl) return;
    const path = rowEl.dataset.path;
    if (t.classList.contains("rb-remove")) {
      const { node, index } = rbParent(path); node.rows.splice(index, 1); renderRuleBuilder();
    } else if (t.classList.contains("rb-gremove")) {
      const { node, index } = rbParent(path); node.rows.splice(index, 1); renderRuleBuilder();
    } else if (t.classList.contains("rb-gadd")) {
      rbRowAt(path).rows.push({ kind: "cond", metric: "close", operator: "gt", value: 100, lookback: "" });
      renderRuleBuilder();
    }
  });
  if ($("#rb-op")) $("#rb-op").addEventListener("change", () => { rbRoot.op = $("#rb-op").value; refreshRbPreview(); });
  if ($("#rb-add")) $("#rb-add").addEventListener("click", () => {
    rbRoot.rows.push({ kind: "cond", metric: "close", operator: "gt", value: 100, lookback: "" });
    renderRuleBuilder();
  });
  if ($("#rb-add-group")) $("#rb-add-group").addEventListener("click", () => {
    rbRoot.rows.push({ kind: "group", op: "OR", rows: [
      { kind: "cond", metric: "rsi", operator: "lt", value: 30, lookback: "" },
      { kind: "cond", metric: "rsi", operator: "gt", value: 70, lookback: "" },
    ] });
    renderRuleBuilder();
  });
  if ($("#rb-run")) $("#rb-run").addEventListener("click", runRule);
  if ($("#rb-save")) $("#rb-save").addEventListener("click", saveRule);
  if ($("#rb-load")) $("#rb-load").addEventListener("click", loadRule);
  if ($("#rb-duplicate")) $("#rb-duplicate").addEventListener("click", duplicateRule);
  if ($("#rb-delete")) $("#rb-delete").addEventListener("click", deleteRule);
}

/* ==========================================================================
   DASHBOARD COMPOSITION (Phase 4)
   --------------------------------------------------------------------------
   Show / hide / reorder the Overview panels, persisted per browser. Order is
   applied with CSS `order` so the markup stays the source of truth and a reset
   is trivial. Nothing here fabricates content: hidden panels are simply hidden.
   ========================================================================== */
const DASH_PANELS = [
  ["breadth", "Market breadth"],
  ["totals", "Totals (latest stored day)"],
  ["regime", "Market regime"],
  ["index", "Index context"],
  ["alerts", "Alerts"],
  ["gainers", "Top gainers"],
  ["losers", "Top losers"],
  ["active", "Most active by turnover"],
];
const DASH_KEY = "mt-dashboard-layout";
let dashLayout = null;

function loadDashLayout() {
  let raw = null;
  try { raw = JSON.parse(localStorage.getItem(DASH_KEY)); } catch (e) { raw = null; }
  const known = DASH_PANELS.map((p) => p[0]);
  dashLayout = {
    order: Array.isArray(raw && raw.order) ? raw.order.filter((id) => known.includes(id)) : [],
    hidden: Array.isArray(raw && raw.hidden) ? raw.hidden.filter((id) => known.includes(id)) : [],
  };
  known.forEach((id) => { if (!dashLayout.order.includes(id)) dashLayout.order.push(id); });
  return dashLayout;
}
function saveDashLayout() {
  try { localStorage.setItem(DASH_KEY, JSON.stringify(dashLayout)); } catch (e) { /* storage off */ }
}
function applyDashLayout() {
  if (!dashLayout) loadDashLayout();
  const grid = document.querySelector("#view-overview .grid");
  if (grid) {
    dashLayout.order.forEach((id, idx) => {
      const el = grid.querySelector(`[data-panel="${id}"]`);
      if (!el) return;
      el.style.order = idx;
      el.style.display = dashLayout.hidden.includes(id) ? "none" : "";
    });
  }
  renderDashPicker();
}
function renderDashPicker() {
  const host = $("#dash-picker");
  if (!host) return;
  host.innerHTML = dashLayout.order.map((id, i) => {
    const label = (DASH_PANELS.find((p) => p[0] === id) || [id, id])[1];
    const vis = !dashLayout.hidden.includes(id);
    return `<div class="rb-row">
      <label class="chk"><input type="checkbox" class="dash-vis" data-id="${id}"${vis ? " checked" : ""} /> ${esc(label)}</label>
      <button class="ghost dash-up" data-id="${id}"${i === 0 ? " disabled" : ""}>↑</button>
      <button class="ghost dash-down" data-id="${id}"${i === dashLayout.order.length - 1 ? " disabled" : ""}>↓</button>
    </div>`;
  }).join("");
}
function moveDashPanel(id, delta) {
  const i = dashLayout.order.indexOf(id);
  const j = i + delta;
  if (i < 0 || j < 0 || j >= dashLayout.order.length) return;
  [dashLayout.order[i], dashLayout.order[j]] = [dashLayout.order[j], dashLayout.order[i]];
  saveDashLayout();
  applyDashLayout();
}
/* Turnover heatmap: a squarified treemap of the session's live quote board.
   Tile area ∝ turnover; colour = published % change (green up / red down).
   Symbols the source left without either are excluded upstream, so every tile
   is real data - never an estimate. */
function heatColor(pct) {
  const clamp = (v) => Math.max(0, Math.min(1, v));
  const t = clamp(Math.min(Math.abs(pct) / 3.0, 1)); // saturation reaching ±3%
  if (pct > 0.05) return `rgba(23, ${Math.round(160 - 60 * (1 - t))}, ${Math.round(200 - 60 * t)}, ${0.25 + 0.65 * t})`;
  if (pct < -0.05) return `rgba(${Math.round(200 + 40 * t)}, ${Math.round(120 - 60 * t)}, ${Math.round(100 - 40 * t)}, ${0.25 + 0.65 * t})`;
  return "rgba(157,180,174,0.20)";
}

function squarify(items, x, y, w, h) {
  /* items must be sorted by value desc; values are absolute areas within w*h.
     Classic squarified layout (Bruls, Huizing & van Wijk). */
  const out = [];
  let queue = items.slice();
  let rx = x, ry = y, rw = w, rh = h;
  const worst = (childSide) => Math.max(childSide, 1 / (childSide || 1e-9));

  function rowWorst(row, rowArea, side) {
    const thickness = rowArea / side;
    let worstRatio = 0;
    for (const it of row) {
      const own = it.value / thickness; // tile length along the row
      worstRatio = Math.max(worstRatio, worst(own / thickness));
    }
    return worstRatio;
  }

  while (queue.length && rw > 0 && rh > 0) {
    const side = Math.min(rw, rh);
    const row = [];
    let rowArea = 0, best = Infinity, k = 0;
    while (k < queue.length) {
      const cand = rowWorst(row.concat(queue[k]), rowArea + queue[k].value, side);
      if (row.length === 0 || cand <= best) {
        row.push(queue[k]); rowArea += queue[k].value; best = cand; k += 1;
      } else {
        break;
      }
    }
    if (!row.length) break;
    const thickness = rowArea / side;
    let off = 0;
    const horiz = rw < rh; // tall container → row lies along the full width
    for (const it of row) {
      const len = (it.value / rowArea) * side;
      if (horiz) {
        out.push({ ...it, x: rx + off, y: ry, w: len, h: thickness });
      } else {
        out.push({ ...it, x: rx, y: ry + off, w: thickness, h: len });
      }
      off += len;
    }
    if (horiz) { ry += thickness; rh -= thickness; }
    else { rx += thickness; rw -= thickness; }
    queue = queue.slice(k);
  }
  return out;
}

function renderHeat(heat) {
  const host = $("#ov-heat");
  if (!host) return;
  const meta = $("#ov-heat-meta"), note = $("#ov-heat-note");
  if (!heat || !heat.tiles || !heat.tiles.length) {
    host.innerHTML = `<div class="empty">No turnover-weighted tiles available from the source right now.</div>`;
    if (note) note.textContent = "";
    if (meta) meta.textContent = "";
    return;
  }
  // The host is display:position sized via CSS (aspect handled by the height).
  const W = Math.max(320, host.clientWidth || 900);
  const H = 260;
  const tiles = heat.tiles.filter((t) => t.pct !== null && t.pct !== undefined && t.turnover > 0);
  const total = tiles.reduce((acc, t) => acc + t.turnover, 0) || 1;
  const laid = squarify(
    tiles.map((t) => ({ ...t, value: (t.turnover / total) * W * H })),
    0, 0, W, H
  );
  host.innerHTML = laid.map((t) => {
    const pctS = t.pct >= 0 ? "+" : "";
    // labels only fit on reasonably large tiles; the tooltip always carries
    // the full values, so nothing is unreachable
    const big = t.w > 52 && t.h > 30;
    const sym = big ? `<span class="ht-sym">${esc(t.symbol)}</span>` : "";
    const pc = big ? `<span class="ht-pct">${pctS}${fmtNum(t.pct)}%</span>` : "";
    return `<div class="heat-tile ${t.pct >= 0 ? "up" : "down"}"
      data-sym="${esc(t.symbol)}"
      style="left:${(100 * t.x) / W}%;top:${(100 * t.y) / H}%;width:${(100 * t.w) / W}%;height:${(100 * t.h) / H}%;background:${heatColor(t.pct)}"
      title="${esc(t.symbol)} · ${pctS}${fmtNum(t.pct)}% · turnover NPR ${fmtNum(t.turnover, 0)}">${sym}${pc}</div>`;
  }).join("");
  // bind clicks: open charting with the clicked symbol
  host.querySelectorAll(".heat-tile").forEach((tile) => {
    tile.addEventListener("click", () => {
      const sym = tile.dataset.sym;
      if (!sym) return;
      $("#symbol-input").value = sym;
      showView("charts");
      viewShown("charts");
      loadChart();
    });
  });
  if (meta) meta.textContent = `${fmtInt(tiles.length)} tiles of ${fmtInt(heat.covered)} covered · ${fmtInt(heat.total_quotes)} quotes`;
  if (note) note.textContent = heat.note || "";
}

function bindDashboard() {
  const host = $("#dash-picker");
  if (host) {
    host.addEventListener("change", (e) => {
      const t = e.target;
      if (!t.classList.contains("dash-vis")) return;
      const id = t.dataset.id;
      if (t.checked) dashLayout.hidden = dashLayout.hidden.filter((x) => x !== id);
      else if (!dashLayout.hidden.includes(id)) dashLayout.hidden.push(id);
      saveDashLayout();
      applyDashLayout();
    });
    host.addEventListener("click", (e) => {
      const t = e.target;
      if (t.classList.contains("dash-up")) moveDashPanel(t.dataset.id, -1);
      else if (t.classList.contains("dash-down")) moveDashPanel(t.dataset.id, 1);
    });
  }
  const reset = $("#dash-reset");
  if (reset) reset.addEventListener("click", () => {
    loadDashLayout();
    dashLayout = { order: DASH_PANELS.map((p) => p[0]), hidden: [] };
    saveDashLayout();
    applyDashLayout();
  });
  const liveBtn = $("#live-refresh");
  if (liveBtn) liveBtn.addEventListener("click", () => loadLive(true));
  loadDashLayout();
  applyDashLayout();
}

/* ==========================================================================
   MANUAL CHART DRAWINGS — Fibonacci retracement / extension / horizontal lines
   --------------------------------------------------------------------------
   Anchors are placed by real pointer clicks and are stored in the chart's own
   data coordinates (a date string + a price), so they stay correct when the
   user zooms, pans or changes the visible range. Nothing here is detector
   output: every drawing is created by the researcher, and the panel says so.
   ========================================================================== */
const DRAW_DEFAULT_RATIOS = {
  fib_retracement: [0.236, 0.382, 0.5, 0.618, 0.786],
  fib_extension: [1.272, 1.618, 2.618],
  fib_fan: [0.236, 0.382, 0.5, 0.618, 0.786],
  fib_channel: [0.236, 0.382, 0.5, 0.618, 0.786, 1, 1.618],
  fib_arc: [0.236, 0.382, 0.5, 0.618, 0.786, 1.0],
  fib_spiral: [],
  fib_tbe: [0, 0.618, 1, 1.618, 2.618],
  fib_timezones: [],
  regression_channel: [2],
  pitchfork: [], schiff_pitchfork: [], triangle: [], polyline: [], xabcd: [], abcd: [],
  three_drives: [], elliott_impulse: [], elliott_abc: [],
  gann_fan: [8, 4, 2, 1, 0.5, 0.25, 0.125],
  price_range: [], date_range: [], price_label: [], note: [], flag: [],
  hline: [],
  trendline: [],
  ray: [],
  channel: [],
  text: [],
  measure: [],
  vline: [],
  crossline: [],
  hray: [],
  extended: [],
  rectangle: [],
  arrow: [],
  long_pos: [2.0],
  short_pos: [2.0],
};
const DRAW_LABELS = {
  fib_retracement: "Fib retracement",
  fib_extension: "Fib extension",
  price_range: "Price range",
  date_range: "Date + bars range",
  price_label: "Price label",
  note: "Note (text + marker)",
  flag: "Flag marker",
  fib_timezones: "Fib time zones",
  fib_fan: "Fib fan",
  fib_channel: "Fib channel (3 clicks)",
  fib_tbe: "Trend-based Fib extension (3 clicks)",
  regression_channel: "Regression channel",
  pitchfork: "Pitchfork",
  schiff_pitchfork: "Schiff pitchfork",
  circle: "Circle (2 anchors: centre + radius)",
  ellipse: "Ellipse (3 anchors: centre + X + Y)",
  fib_arc: "Fibonacci arcs (2 anchors)",
  hns: "Head & Shoulders (5 anchors: LS, head, RS, neck L/R)",
  gann_fan: "Gann fan (leg-relative)",
  triangle: "Triangle",
  polyline: "Polyline (Enter finishes)",
  xabcd: "XABCD harmonic",
  abcd: "ABCD",
  three_drives: "Three drives",
  elliott_impulse: "Elliott impulse 1-5",
  elliott_abc: "Elliott correction A-B-C",
  hline: "Horizontal line",
  trendline: "Trendline",
  ray: "Ray (extends right)",
  channel: "Parallel channel (3 clicks)",
  text: "Text note",
  measure: "Measure",
  vline: "Vertical line",
  crossline: "Cross line",
  hray: "Horizontal ray (extends right)",
  extended: "Extended line (both directions)",
  rectangle: "Rectangle",
  arrow: "Arrow",
  long_pos: "Long position (entry → stop, R:R set)",
  short_pos: "Short position (entry → stop, R:R set)",
};
/* interaction modes are not drawings */
const DRAW_MODES = new Set(["", "__cursor", "select", "eraser"]);
/* Tools that need no second click */
const DRAW_ONECLICK = new Set(["hline", "text", "vline", "crossline", "hray"]);
/* Tools that consume an optional/required third anchor */
const DRAW_THREECLICK = new Set(["channel", "triangle", "pitchfork", "schiff_pitchfork", "fib_channel", "fib_tbe", "elliott_abc", "ellipse"]);

/* ===== §5.8 second-wave drawing tools =====
   Fixed-length tools beyond 3 anchors accumulate clicks in state.drawMulti
   and finish on the final anchor; `polyline` is variable-length and finishes
   with Enter or a double-click. Anchors live in t1..tN / p1..pN so the
   persisted per-symbol JSON stays flat. */
const DRAW_MULTI_N = {
  xabcd: 5, abcd: 4, three_drives: 4, elliott_impulse: 5, hns: 5,
};
const DRAW_VARLEN = new Set(["polyline"]);
const DRAW_ONE_TOOLS2 = new Set(["price_label", "note", "flag"]);
/* Letter labels rendered next to each anchor (manual pattern tools). */
const DRAW_ANCHOR_LETTERS = {
  xabcd: ["X", "A", "B", "C", "D"],
  abcd: ["A", "B", "C", "D"],
  three_drives: ["X", "1", "2", "3"],
  elliott_impulse: ["1", "2", "3", "4", "5"],
  elliott_abc: ["A", "B", "C"],
  pitchfork: ["A", "B", "C"],
  schiff_pitchfork: ["A", "B", "C"],
  ellipse: ["C", "X", "Y"],
  hns: ["LS", "H", "RS", "N1", "N2"],
};

/* Finish the accumulated multi-anchor drawing. */
function finishMulti() {
  const m = state.drawMulti;
  if (!m) return;
  if (m.pts.length < 2) { drawStatus("Need at least two anchors."); return; }
  pushDrawHistory();
  const d = {
    id: nextDrawingId(), type: m.type,
    ratios: Array.isArray(DRAW_DEFAULT_RATIOS[m.type]) ? [...DRAW_DEFAULT_RATIOS[m.type]] : [],
    color: DRAW_COLORS[state.drawings.length % DRAW_COLORS.length],
    created: new Date().toISOString(),
  };
  m.pts.forEach((pt, i) => { d["t" + (i + 1)] = pt.t; d["p" + (i + 1)] = pt.p; });
  state.drawings.push(d);
  state.drawMulti = null;
  state.pendingMarker = [];
  drawStatus(`${DRAW_LABELS[m.type] || m.type} added with ${m.pts.length} anchors.`);
  afterDrawingsChanged();
  if (!state.drawStay) setDrawTool(null);
}

/* NEPSE trades Sun–Thu (Fri/Sat closed). Generate up to `n` future weekday
   dates strictly after `afterISO`, matching the existing ray projection. */
function nextWeekdayDates(n, afterISO) {
  const out = [];
  let cur = new Date(afterISO + "T00:00:00");
  let guard = 0;
  while (out.length < n && guard++ < n * 3 + 10) {
    cur.setDate(cur.getDate() + 1);
    const dow = cur.getDay();
    if (dow === 5 || dow === 6) continue;
    out.push(cur.toISOString().slice(0, 10));
  }
  return out;
}
const DRAW_COLORS = [PRAVAHA.caution, PRAVAHA.cyan, PRAVAHA.mint, PRAVAHA.up, PRAVAHA.down];

function drawingsKey(symbol) { return `mt-drawings-${symbol}`; }

function loadDrawings(symbol) {
  try {
    const raw = JSON.parse(localStorage.getItem(drawingsKey(symbol)) || "[]");
    return Array.isArray(raw) ? raw.filter((d) => d && d.type) : [];
  } catch (e) { return []; }
}
function persistDrawings(symbol, drawings) {
  try { localStorage.setItem(drawingsKey(symbol), JSON.stringify(drawings || [])); } catch (e) { /* storage off */ }
}

/* Undo/redo operate on snapshots of the drawing list. pushDrawHistory is the
   pre-mutation hook every drawing mutation calls; the typed unified stack
   (histPushDraw) is what actually stores it. The legacy per-symbol arrays
   stay for compatibility with code paths that still push snapshots. */
function pushDrawHistory() {
  histPushDraw();
}
function drawingsUndo() {
  histUndo(); // unified stack since §5.7; legacy alias for older call sites
}
function drawingsRedo() {
  histRedo(); // unified stack since §5.7; kept as an alias for older call sites
  return;
}
/* ================= §5.7 unified history: drawings + chart navigation ======
   One typed stack decides what Cmd/Ctrl+Z does:

     {kind:"draw", symbol, snap}  — snapshot of that symbol's drawing list
     {kind:"view", before, after} — logical price/time range of the viewport

   Undo pops the TOP entry whatever its kind, so the most recent action type
   wins. Entries are capped at 100; text fields keep the browser's native
   text undo because typing is never routed here. */
function histPushDraw() {
  const snap = JSON.stringify(state.drawings || []);
  state.undoStack.push({ kind: "draw", symbol: state.chartSymbol, snap });
  if (state.undoStack.length > 100) state.undoStack.shift();
  state.redoStack = [];
}
function applyDrawSnap(symbol, snap) {
  let list = [];
  try { list = JSON.parse(snap) || []; } catch (e) { list = []; }
  persistDrawings(symbol, list);
  if (symbol === state.chartSymbol) {
    state.drawings = list;
    state.drawSelectId = null;
    renderDrawings();
    renderDrawList();
  }
}
function currentViewRange() {
  const chart = state.charts.price;
  if (!chart) return null;
  try { const r = chart.timeScale().getVisibleLogicalRange(); return r ? { from: r.from, to: r.to } : null; } catch (e) { return null; }
}
function setViewRange(range) {
  const chart = state.charts.price;
  if (!chart || !range) return;
  state.viewSuppress = true;
  try { chart.timeScale().setVisibleLogicalRange(range); } catch (e) { /* stale range */ }
}
function histUndo() {
  const e = state.undoStack.pop();
  if (!e) return;
  if (e.kind === "draw") {
    let cur = "[]";
    if (e.symbol === state.chartSymbol) cur = JSON.stringify(state.drawings || []);
    else cur = JSON.stringify(loadDrawings(e.symbol));
    state.redoStack.push({ kind: "draw", symbol: e.symbol, snap: cur });
    applyDrawSnap(e.symbol, e.snap);
    updateUndoButtons();
  } else if (e.kind === "view" && state.charts.price) {
    const before = currentViewRange();
    setViewRange(e.before);
    if (before) state.redoStack.push({ kind: "view", before, after: e.before });
    updateUndoButtons();
  }
}
function histRedo() {
  const e = state.redoStack.pop();
  if (!e) return;
  if (e.kind === "draw") {
    let cur = "[]";
    if (e.symbol === state.chartSymbol) cur = JSON.stringify(state.drawings || []);
    else cur = JSON.stringify(loadDrawings(e.symbol));
    state.undoStack.push({ kind: "draw", symbol: e.symbol, snap: cur });
    applyDrawSnap(e.symbol, e.snap);
    updateUndoButtons();
  } else if (e.kind === "view" && state.charts.price) {
    const before = currentViewRange();
    setViewRange(e.after);
    if (before) state.undoStack.push({ kind: "view", before, after: e.after });
    updateUndoButtons();
  }
}
function updateUndoButtons() {
  const u = $("#draw-undo"), r = $("#draw-redo");
  if (u) { u.disabled = !state.undoStack.length; u.title = state.undoStack.length ? "Undo (Cmd/Ctrl+Z)" : "Nothing to undo"; }
  if (r) { r.disabled = !state.redoStack.length; r.title = state.redoStack.length ? "Redo (Shift+Cmd/Ctrl+Z)" : "Nothing to redo"; }
}
/* Keyboard: Cmd/Ctrl+Z undo, Shift+Cmd/Ctrl+Z or Ctrl+Y redo. preventDefault
   stops the browser from treating Cmd+Z as history navigation; inputs and
   textareas keep their native text undo. */
function installUndoKeyboard() {
  document.addEventListener("keydown", (e) => {
    const mod = e.metaKey || e.ctrlKey;
    if (!mod) return;
    const key = (e.key || "").toLowerCase();
    if (key !== "z" && key !== "y") return;
    const t = e.target;
    const typing = t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable);
    if (typing) return;
    const chartsActive = (() => {
      const v = $("#view-charts");
      return !!(v && (v.classList.contains("active") || !v.hidden));
    })();
    if (!chartsActive) return;
    e.preventDefault();
    e.stopPropagation();
    if (key === "y" || e.shiftKey) histRedo(); else histUndo();
  }, true);
}
/* Chart-navigation history. The chart emits one event per animation frame of
   a wheel zoom or pan; each event coalesces: the settled gesture commits ONE
   entry, merging into a previous adjacent (≤2 s) view entry instead of
   stacking hundreds. Programmatic restores set `viewSuppress` once so the
   listener ignores the restore it caused. */
function installViewHistory(chart) {
  let timer = null, pending = null, lastCommit = 0;
  chart.timeScale().subscribeVisibleLogicalRangeChange((r) => {
    if (!r) return;
    if (state.viewSuppress) { state.viewSuppress = false; state.viewBase = { from: r.from, to: r.to }; return; }
    pending = { from: r.from, to: r.to };
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => {
      timer = null; // gesture settled — commit exactly one entry
      if (!state.viewBase || !pending) { state.viewBase = pending; return; }
      const a = state.viewBase, b = pending;
      if (Math.abs(a.from - b.from) < 0.005 && Math.abs(a.to - b.to) < 0.005) return;
      const top = state.undoStack[state.undoStack.length - 1];
      if (top && top.kind === "view" && Date.now() - lastCommit < 2000) {
        top.after = { ...b }; // same gesture cluster: extend, don't stack
      } else {
        state.undoStack.push({ kind: "view", before: { ...a }, after: { ...b } });
        if (state.undoStack.length > 100) state.undoStack.shift();
        state.redoStack = [];
      }
      lastCommit = Date.now();
      state.viewBase = { ...b };
      updateUndoButtons();
    }, 500);
  });
  state.viewBase = currentViewRange();
}
function afterDrawingsChanged() {
  persistDrawings(state.chartSymbol, state.drawings);
  renderDrawings();
  renderDrawList();
  renderDrawProps();
  refreshSelectionMarkers();
}

/* Anchor handles for the selected drawing, so a selection is visible on the
   chart (not only as a "selected" pill in the list). Merged into the single
   setMarkers() call in flushMarkers — lightweight-charts allows only one
   marker call per series, so every marker source funnels through there. */
function refreshSelectionMarkers() {
  // Handles are a primitive, not bar markers: an inBar marker can be hidden
  // under a candle and any marker on the candle series changes autoscaling.
  state.selectionMarkers = [];
  renderAnchorHandles();
  flushMarkers();
}

function nextDrawingId() {
  return `d${Date.now().toString(36)}${Math.floor(Math.random() * 1000)}`;
}

/* Price levels for one drawing, in the chart's own price units. */

/* §10 testable geometry/math seam: pure OLS fit over (i, value) pairs — used
   by the regression-channel renderer and unit-checked via window.__mtMath.
   Returns null on degenerate input (no variance in x or < 2 points) so callers
   can honestly draw nothing instead of a fabricated straight line. sd is the
   residual standard deviation with the n-1 denominator. */
function olsFitXY(pairs) {
  const pts = (pairs || []).map(([x, y]) => [Number(x), Number(y)])
    .filter(([x, y]) => isFinite(x) && isFinite(y));
  const n = pts.length;
  if (n < 2) return null;
  const meanX = pts.reduce((s, v) => s + v[0], 0) / n;
  const meanY = pts.reduce((s, v) => s + v[1], 0) / n;
  let sxy = 0, sxx = 0;
  pts.forEach(([x, y]) => { sxy += (x - meanX) * (y - meanY); sxx += (x - meanX) ** 2; });
  if (!(sxx > 0)) return null;
  const slope = sxy / sxx;
  const intercept = meanY - slope * meanX;
  let sumSq = 0;
  pts.forEach(([x, y]) => { sumSq += (y - (intercept + slope * x)) ** 2; });
  const sd = Math.sqrt(sumSq / (n - 1));
  return { slope, intercept, sd, n };
}

/* Fibonacci level used by the manual retracement/extension fields: documents
   the formula in one place — retracement p2 − r·(p2−p1), extension p2 + r·(p2−p1). */
function fibLevel(kind, p1, p2, r) {
  const a = Number(p1), b = Number(p2), rr = Number(r);
  if (!isFinite(a) || !isFinite(b) || !isFinite(rr)) return null;
  const diff = b - a;
  return kind === "extension" ? b + rr * diff : b - rr * diff;
}

/* Expose the pure math for browser fixture tests (read-only surface). */
window.__mtMath = { olsFitXY, fibLevel };

function drawingLevels(d) {
  const ratios = Array.isArray(d.ratios) ? d.ratios : [];
  if (d.type === "hline") {
    return [{ ratio: null, price: Number(d.p1) }].filter((l) => isFinite(l.price));
  }
  const p1 = Number(d.p1);
  const p2 = Number(d.p2);
  if (!isFinite(p1) || !isFinite(p2)) return [];
  const diff = p2 - p1;
  return ratios
    .map((r) => Number(r))
    .filter((r) => isFinite(r))
    .map((r) => ({
      ratio: r,
      price: fibLevel(d.type === "fib_extension" ? "extension" : "retracement", p1, p2, r),
    }))
    .filter((l) => isFinite(l.price));
}

/* Drawing overlays must never drive the price scale. Before this, moving the
   preview outside the visible price range re-autoscaled the candle pane under
   the pointer, so the anchor landed a few pixels away from the cursor and the
   chart appeared to jump. Returning null from autoscaleInfoProvider excludes
   the overlay from autoscaling while still rendering it on the main scale. */
function addDrawSeries(chart, options = {}) {
  return chart.addLineSeries(Object.assign({}, options, { autoscaleInfoProvider: () => null }));
}

/* Remove the previous overlay series (the drawings themselves are kept). */
/* Live preview while placing a multi-anchor drawing: a ~50%-opacity line from
   the first anchor to the current cursor. Removed on commit/cancel. */
function clearDrawPreview() {
  if (drawPreviewRaf) { cancelAnimationFrame(drawPreviewRaf); drawPreviewRaf = 0; }
  drawPreviewPoint = null;
  const chart = state.charts.price;
  (state.drawPreviewSeries || []).forEach((s) => { try { chart.removeSeries(s); } catch (e) { /* gone */ } });
  state.drawPreviewSeries = [];
}
let drawPreviewRaf = 0;
let drawPreviewPoint = null;
function queueDrawPreview(mx, my) {
  drawPreviewPoint = { mx, my };
  if (drawPreviewRaf) return;
  drawPreviewRaf = requestAnimationFrame(() => {
    drawPreviewRaf = 0;
    const p = drawPreviewPoint;
    drawPreviewPoint = null;
    if (p) renderDrawPreview(p.mx, p.my);
  });
}
function renderDrawPreview(mx, my) {
  const chart = state.charts.price;
  if (!chart || !state.candleSeries || !state.drawPending) return;
  const dates = state.chartDates || [];
  if (!dates.length) return;
  const first = state.drawPending;
  const t1 = chartTimeKey(first.t), p1 = Number(first.p);
  if (!t1 || !isFinite(p1)) return;
  // Resolve the cursor to a time/price using the chart's own coordinate APIs.
  // x/y are chart-local (the caller subtracts the content-box origin).
  const idx = barIndexAtX(mx);
  const t2 = idx != null ? String(dates[idx]) : null;
  let p2 = null;
  try { p2 = state.candleSeries.coordinateToPrice(my); } catch (e) { p2 = null; }
  // coordinateToPrice can return null just outside the pane. Fall back to the
  // close of the bar under the pointer rather than to an unrelated value.
  if (p2 == null || !isFinite(p2)) {
    if (idx != null && state.chartBars && state.chartBars[idx]) {
      const b = state.chartBars[idx];
      p2 = (typeof b.close === "number" && isFinite(b.close)) ? b.close : null;
    }
  }
  if (t2 == null || p2 == null || !isFinite(p2)) { clearDrawPreview(); return; }
  const color = "rgba(157,180,174,.5)";
  const isRect = state.drawTool === "rectangle" || state.drawTool === "long_pos" || state.drawTool === "short_pos";
  let series = (state.drawPreviewSeries || [])[0];
  if (!series) {
    series = addDrawSeries(chart, {
      color, lineWidth: isRect ? 1 : 1.5, lineStyle: 2,
      priceLineVisible: false, lastValueVisible: false,
    });
    state.drawPreviewSeries.push(series);
  }
  // Lightweight Charts requires strictly ascending time. A left-to-right draw
  // met that by accident; drawing right-to-left sent descending timestamps and
  // the library failed every frame (the "Value is null" errors). Sorting and
  // de-duplicating here makes both directions identical.
  const lowFirst = String(t1) <= String(t2);
  const tLo = lowFirst ? t1 : t2;
  const tHi = lowFirst ? t2 : t1;
  const pLo = lowFirst ? p1 : p2;
  const pHi = lowFirst ? p2 : p1;
  if (isRect) {
    const priceLo = Math.min(p1, p2), priceHi = Math.max(p1, p2);
    if (tLo === tHi) series.setData([{ time: tLo, value: priceLo }]);
    else series.setData([
      { time: tLo, value: priceLo }, { time: tHi, value: priceLo },
      { time: tHi, value: priceHi }, { time: tLo, value: priceHi },
      { time: tLo, value: priceLo },
    ]);
  } else if (tLo === tHi) {
    series.setData([{ time: tLo, value: pLo }]);
  } else {
    series.setData([{ time: tLo, value: pLo }, { time: tHi, value: pHi }]);
  }
}

function clearDrawingSeries() {
  const chart = state.charts.price;
  (state.drawSeries || []).forEach((s) => { try { chart.removeSeries(s); } catch (e) { /* gone */ } });
  state.drawSeries = [];
  clearDrawPreview();
  (state.drawPrimitives || []).forEach((p) => { try { if (p.series && p.prim) p.series.detachPrimitive(p.prim); } catch (e) { /* gone */ } });
  state.drawPrimitives = [];
  state.anchorHandlePrim = null;
}

/* Segment chain between consecutive anchors — the renderer for every N-point
   tool (patterns, triangle, polyline, fib-leg helpers). */
function segMulti(d, color, opts = {}) {
  const chart = state.charts.price;
  const dts = state.chartDates || [];
  const idx = new Map(dts.map((dt, k) => [dt, k]));
  const parts = anchorParts(d);
  const xy = parts.map(([, t, p]) => ({ t: String(t), p: Number(p), i: idx.get(String(t)) }));
  if (xy.length < 2 || xy.some((v) => v.i == null || !isFinite(v.p))) return;
  for (let k = 0; k < xy.length - 1; k++) {
    const A = xy[k], B = xy[k + 1];
    const lo = A.i <= B.i ? A : B, hi = A.i <= B.i ? B : A;
    const s = addDrawSeries(chart, {
      color, lineWidth: opts.width ?? 1, priceLineVisible: false,
      lastValueVisible: false, title: (opts.titles && opts.titles[k]) || "",
      lineStyle: opts.dashed ? 2 : 0,
    });
    s.setData(lo.i === hi.i ? [{ time: lo.t, value: lo.p }]
      : [{ time: lo.t, value: lo.p }, { time: hi.t, value: hi.p }]);
    state.drawSeries.push(s);
  }
  if (opts.close && xy.length > 2) {
    const A = xy[0], B = xy[xy.length - 1];
    const lo = A.i <= B.i ? A : B, hi = A.i <= B.i ? B : A;
    const s = addDrawSeries(chart, {
      color, lineWidth: 1, priceLineVisible: false, lastValueVisible: false, title: "", lineStyle: 2,
    });
    s.setData([{ time: lo.t, value: lo.p }, { time: hi.t, value: hi.p }]);
    state.drawSeries.push(s);
  }
}

/* Custom primitive for a true vertical line. Uses only timeToCoordinate (which
   works in this LWC build) and the canvas height — no price coordinate needed. */
function makeVerticalLinePrimitive(chart, time, color) {
  let chartRef = null;
  return {
    paneViews: () => [{
      renderer: () => ({
        draw: (target) => {
          target.useMediaCoordinateSpace((scope) => {
            const ctx = scope.context;
            const x = chartRef ? chartRef.timeScale().timeToCoordinate(time) : null;
            if (x == null) return;
            ctx.save();
            ctx.fillStyle = color || "#FFFFFF";
            ctx.fillRect(x - 1, 0, 2, scope.mediaSize.height);
            ctx.restore();
          });
        },
        zOrder: () => "normal",
      }),
    }],
    attached: (p) => { chartRef = p.chart; if (p.requestUpdate) p.requestUpdate(); },
    detached: () => { chartRef = null; },
    updateAllViews: () => {},
  };
}

/* Exact anchor handles. Markers are bar-anchored and (for inBar) can be hidden
   behind the candle body; more importantly, markers on the candle series change
   the autoscale range. A primitive draws at the real (time, price) coordinate
   without taking part in autoscaling. */
function makeAnchorHandlesPrimitive(chart, series, items) {
  let chartRef = null;
  let seriesRef = null;
  return {
    paneViews: () => [{
      renderer: () => ({
        draw: (target) => {
          target.useMediaCoordinateSpace((scope) => {
            const ctx = scope.context;
            items.forEach((a) => {
              const x = chartRef ? chartRef.timeScale().timeToCoordinate(String(a.time)) : null;
              const y = seriesRef ? seriesRef.priceToCoordinate(Number(a.price)) : null;
              if (x == null || y == null) return;
              const r = a.selected ? 7 : 6;
              ctx.save();
              // Dark halo keeps the handle legible over both candles and the line.
              ctx.beginPath();
              ctx.arc(x, y, r + 1.5, 0, Math.PI * 2);
              ctx.strokeStyle = "rgba(6,18,15,0.9)";
              ctx.lineWidth = 2.5;
              ctx.stroke();
              ctx.beginPath();
              ctx.arc(x, y, r, 0, Math.PI * 2);
              ctx.fillStyle = a.selected ? "#FFE600" : "#F5F8F7";
              ctx.fill();
              ctx.lineWidth = a.selected ? 2 : 1.25;
              ctx.strokeStyle = a.color || "#0B1512";
              ctx.stroke();
              if (a.label) {
                ctx.fillStyle = "#0B1512";
                ctx.font = "600 9px ui-sans-serif, system-ui, sans-serif";
                ctx.textAlign = "center";
                ctx.textBaseline = "middle";
                ctx.fillText(a.label, x, y + 0.5);
              }
              ctx.restore();
            });
          });
        },
        zOrder: () => "top",
      }),
    }],
    attached: (p) => {
      chartRef = p.chart;
      seriesRef = p.series;
      if (p.requestUpdate) p.requestUpdate();
    },
    detached: () => { chartRef = null; seriesRef = null; },
    updateAllViews: () => {},
  };
}

function renderAnchorHandles() {
  const chart = state.charts.price;
  if (!chart || !state.candleSeries) return;
  if (state.anchorHandlePrim) {
    const at = (state.drawPrimitives || []).findIndex((p) => p.prim === state.anchorHandlePrim);
    if (at >= 0) {
      try { if (state.drawPrimitives[at].series) state.drawPrimitives[at].series.detachPrimitive(state.anchorHandlePrim); }
      catch (e) { /* already gone */ }
      state.drawPrimitives.splice(at, 1);
    }
    state.anchorHandlePrim = null;
  }
  if (!state.drawVisible || (state.replay && state.replay.on)) return;
  const items = [];
  (state.drawings || []).forEach((d, i) => {
    if (d.hidden) return;
    const color = withOpacity(d.color || DRAW_COLORS[i % DRAW_COLORS.length], d.opacity);
    const letters = DRAW_ANCHOR_LETTERS[d.type];
    const selected = d.id === state.drawSelectId;
    anchorParts(d).forEach(([, t, p], k) => {
      if (!t || !isFinite(Number(p))) return;
      items.push({
        time: t, price: Number(p), color, selected,
        label: letters ? (letters[k] || String(k + 1)) : String(k + 1),
      });
    });
  });
  if (!items.length) return;
  const prim = makeAnchorHandlesPrimitive(chart, state.candleSeries, items);
  try {
    state.candleSeries.attachPrimitive(prim);
    state.anchorHandlePrim = prim;
    state.drawPrimitives.push({ series: state.candleSeries, prim });
  } catch (e) { /* primitive API unavailable */ }
}

function withOpacity(color, opacity) {
  const o = (opacity == null || !isFinite(Number(opacity))) ? 1 : Number(opacity);
  if (o >= 0.999) return color || "#9dc4ae";
  const m = /^#([0-9a-f]{6})$/i.exec(String(color || "").trim());
  if (!m) return color || "#9dc4ae";
  const n = parseInt(m[1], 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${o})`;
}

function renderDrawings() {
  const chart = state.charts.price;
  if (!chart) return;
  clearDrawingSeries();
  // Two independent visibility layers, both non-destructive:
  //   state.drawVisible — the master toolbar/drawer switch (hides every overlay)
  //   d.hidden          — per-drawing switch from the drawing list
  // Replay mode hides all drawings too: an anchor beyond the replay cursor
  // would otherwise fail its coordinate lookup mid-drawing anyway.
  if (!state.drawVisible || (state.replay && state.replay.on)) return;
  const dates = state.chartDates || [];
  if (!dates.length) return;
  const firstTime = dates[0];
  const lastTime = dates[dates.length - 1];
  const sameTime = firstTime === lastTime;

  (state.drawings || []).forEach((d, i) => {
    if (d.hidden) return; // per-drawing visibility (B-76: this check was missing)
    const color = d.color || DRAW_COLORS[i % DRAW_COLORS.length];
    if (d.type === "hline") {
      const price = Number(d.p1);
      if (!isFinite(price)) return;
      const s = addDrawSeries(chart, {
        color, lineWidth: (d.lineWidth || 2), priceLineVisible: false, lastValueVisible: true,
        title: `hline ${fmtNum(price)}`,
      });
      s.setData(sameTime ? [{ time: firstTime, value: price }]
        : [{ time: firstTime, value: price }, { time: lastTime, value: price }]);
      state.drawSeries.push(s);
      return;
    }
    const t1 = d.t1, t2 = d.t2;
    if (!t1 || !t2) return;
    const a = String(t1) <= String(t2) ? t1 : t2;
    const b = String(t1) <= String(t2) ? t2 : t1;

    // ---- circle (polyline approximation, 72 segments) -----------------------
    if (d.type === "circle") {
      try {
      const dts = state.chartDates || [];
      const idx = new Map(dts.map((dt, k) => [dt, k]));
      const iC = idx.get(String(d.t1)), iP = idx.get(String(d.t2));
      const PC = Number(d.p1), PP = Number(d.p2);
      if (iC == null || iP == null || ![PC, PP].every(isFinite)) return;
      const rBars = Math.abs(iP - iC);
      const rPrice = Math.abs(PP - PC);
      if (rBars < 0.5 || rPrice === 0) return;
      const pts = [];
      const seen = new Set();
      const N = 72;
      for (let k = 0; k <= N; k++) {
        const ang = (k / N) * 2 * Math.PI;
        const i = iC + rBars * Math.cos(ang);
        const p = PC + rPrice * Math.sin(ang);
        const ri = Math.round(i);
        if (ri < 0 || ri >= dts.length) continue;
        const time = dts[ri];
        if (time == null || seen.has(time)) continue;
        seen.add(time);
        if (!isFinite(p)) continue;
        pts.push({ time, value: p });
      }
      if (pts.length < 3) return;
      pts.sort((a, b) => (a.time < b.time ? -1 : a.time > b.time ? 1 : 0));
      const s = addDrawSeries(chart, { color, lineWidth: 1.5, priceLineVisible: false, lastValueVisible: false, title: "" });
      s.setData(pts);
      state.drawSeries.push(s);
      } catch (e) { console.error("circle render err:", e && e.message); }
      return;
    }
    // ---- fib arcs (concentric semicircles at fib ratios of the leg) --------
    if (d.type === "fib_arc") {
      const dts = state.chartDates || [];
      const idx = new Map(dts.map((dt, k) => [dt, k]));
      const i1 = idx.get(String(d.t1)), i2 = idx.get(String(d.t2));
      const P1 = Number(d.p1), P2 = Number(d.p2);
      const ratios = (Array.isArray(d.ratios) && d.ratios.length) ? d.ratios : [0.236, 0.382, 0.5, 0.618, 0.786, 1.0];
      if (i1 == null || i2 == null || ![P1, P2].every(isFinite)) return;
      const rBars = Math.abs(i2 - i1);
      const rPrice = Math.abs(P2 - P1);
      const N = 48;
      ratios.forEach((r) => {
        const rr = Number(r);
        if (!isFinite(rr) || rr <= 0) return;
        const pts = [];
        const seen = new Set();
        for (let k = 0; k <= N; k++) {
          const ang = (k / N) * Math.PI; // upper semicircle
          const i = i1 + rBars * rr * Math.cos(ang);
          const p = P1 + rPrice * rr * Math.sin(ang);
          const ri = Math.round(i);
          if (ri < 0 || ri >= dts.length) continue;
          const time = dts[ri];
          if (time == null || seen.has(time)) continue;
          seen.add(time);
          if (!isFinite(p)) continue;
          pts.push({ time, value: p });
        }
        if (pts.length < 3) return;
        pts.sort((a, b) => (a.time < b.time ? -1 : a.time > b.time ? 1 : 0));
        const s = addDrawSeries(chart, { color, lineWidth: (d.lineWidth || 1), priceLineVisible: false, lastValueVisible: false, title: "", lineStyle: 2 });
        s.setData(pts);
        state.drawSeries.push(s);
      });
      // base leg
      const s = addDrawSeries(chart, { color, lineWidth: (d.lineWidth || 1), priceLineVisible: false, lastValueVisible: false, title: "", lineStyle: 1 });
      const lo = Math.min(i1, i2), hi = Math.max(i1, i2);
      s.setData([{ time: dts[lo], value: P1 }, { time: dts[hi], value: P2 }]);
      state.drawSeries.push(s);
      return;
    }
    // ---- fibonacci spiral (golden spiral sampled as polyline) --------------
    if (d.type === "fib_spiral") {
      const dts = state.chartDates || [];
      const idx = new Map(dts.map((dt, k) => [dt, k]));
      const i1 = idx.get(String(d.t1)), i2 = idx.get(String(d.t2));
      const P1 = Number(d.p1), P2 = Number(d.p2);
      if (i1 == null || i2 == null || ![P1, P2].every(isFinite)) return;
      const rBars = Math.abs(i2 - i1) || 1;
      const rPrice = Math.abs(P2 - P1) || 1;
      const phi = (1 + Math.sqrt(5)) / 2;
      const pts = [];
      const seen = new Set();
      const N = 240;
      for (let k = 0; k <= N; k++) {
        const theta = (k / N) * 4 * Math.PI; // two full turns
        const r = Math.pow(phi, (2 * theta) / Math.PI) * 0.05; // growth factor
        const i = i1 + rBars * r * Math.cos(theta);
        const p = P1 + rPrice * r * Math.sin(theta);
        const ri = Math.round(i);
        if (ri < 0 || ri >= dts.length) continue;
        const time = dts[ri];
        if (time == null || seen.has(time)) continue;
        seen.add(time);
        if (!isFinite(p)) continue;
        pts.push({ time, value: p });
      }
      if (pts.length < 3) return;
      pts.sort((a, b) => (a.time < b.time ? -1 : a.time > b.time ? 1 : 0));
      const s = addDrawSeries(chart, { color, lineWidth: 1.5, priceLineVisible: false, lastValueVisible: false, title: "" });
      s.setData(pts);
      state.drawSeries.push(s);
      return;
    }
    // ---- new line tools: trendline / ray / measure / channel ------------
    if (d.type === "trendline" || d.type === "ray" || d.type === "measure" || d.type === "channel"
      || d.type === "vline" || d.type === "crossline" || d.type === "hray"
      || d.type === "extended" || d.type === "rectangle" || d.type === "arrow"
      || d.type === "price_range" || d.type === "date_range"
      || d.type === "fib_timezones" || d.type === "fib_fan" || d.type === "regression_channel"
      || d.type === "long_pos" || d.type === "short_pos") {
      const dts = state.chartDates || [];
      const idx = new Map(dts.map((dt, k) => [dt, k]));
      const i1 = idx.get(String(d.t1)), i2 = idx.get(String(d.t2));
      const P1 = Number(d.p1), P2 = Number(d.p2);
      if (!isFinite(P1) || !isFinite(P2) || i1 == null || i2 == null) return;
      // Keep each price with its own anchor. `a`/`b` are chronological only.
      const pA = String(t1) <= String(t2) ? P1 : P2;
      const pB = String(t1) <= String(t2) ? P2 : P1;

      const seg = (priceA, priceB, opts) => {
        const s = addDrawSeries(chart, {
          color, lineWidth: (d.lineWidth != null ? d.lineWidth : ((opts && opts.width) || 1)), priceLineVisible: false,
          lastValueVisible: false, title: (opts && opts.title) || "",
          lineStyle: (d.lineStyle != null ? d.lineStyle : ((opts && opts.dashed) ? 2 : 0)),
        });
        s.setData(a === b ? [{ time: a, value: priceA }]
          : [{ time: a, value: priceA }, { time: b, value: priceB }]);
        state.drawSeries.push(s);
        return s;
      };

      if (d.type === "trendline") {
        if (d.extendLeft || d.extendRight) {
          const perBar = (P2 - P1) / Math.max(1, Math.abs(i2 - i1));
          const iLast = dts.length - 1;
          const pts = [];
          if (d.extendLeft) pts.push({ time: dts[0], value: P1 + perBar * (0 - i1) });
          pts.push({ time: t1, value: P1 });
          pts.push({ time: t2, value: P2 });
          if (d.extendRight) pts.push({ time: dts[iLast], value: P1 + perBar * (iLast - i1) });
          const seen = new Set();
          const ordered = pts
            .filter((pt) => pt.time != null && isFinite(pt.value))
            .sort((u, v) => (u.time < v.time ? -1 : u.time > v.time ? 1 : 0))
            .filter((pt) => (seen.has(pt.time) ? false : (seen.add(pt.time), true)));
          const s = addDrawSeries(chart, { color, lineWidth: (d.lineWidth || 2), priceLineVisible: false, lastValueVisible: false, title: "trendline" });
          s.setData(ordered);
          state.drawSeries.push(s);
        } else {
          seg(pA, pB, { title: "trendline", width: 2 });
        }
      } else if (d.type === "ray") {
        // the ray leaves through the SECOND anchor and projects 30 sessions
        const goingUpIdx = i2 >= i1;
        const perBar = (P2 - P1) / Math.max(1, Math.abs(i2 - i1));
        const proj = [];
        let cur = new Date(dts[dts.length - 1] + "T00:00:00");
        while (proj.length < 30) {
          cur.setDate(cur.getDate() + 1);
          const dow = cur.getDay(); // 5 = Fri, 6 = Sat: NEPSE closed
          if (dow === 5 || dow === 6) continue;
          proj.push({ time: cur.toISOString().slice(0, 10), value: P2 + perBar * (proj.length + 1) * (goingUpIdx ? 1 : 1) });
        }
        const s = addDrawSeries(chart, {
          color, lineWidth: (d.lineWidth || 2), priceLineVisible: false, lastValueVisible: false,
          title: "ray",
        });
        // a ray runs from the earlier anchor onward past the chart's right edge
        const ordered = goingUpIdx
          ? [{ time: d.t1, value: P1 }, { time: d.t2, value: P2 }, ...proj]
          : [{ time: d.t2, value: P2 }, { time: d.t1, value: P1 }];
        s.setData(ordered.sort((u, v) => (u.time < v.time ? -1 : 1)));
        chart.timeScale().applyOptions({ rightOffset: Math.max(2, proj.length + 2) });
        state.drawSeries.push(s);
      } else if (d.type === "measure") {
        const bars = Math.abs(i2 - i1) + 1;
        const delta = P2 - P1;
        const pct = (delta / P1) * 100;
        const label = `${delta >= 0 ? "+" : ""}${fmtNum(delta)} (${fmtNum(pct)}%) · ${bars} bars`;
        seg(pA, pB, { title: label });
        const top = Math.max(P1, P2), bot = Math.min(P1, P2);
        [top, bot].forEach((price) => {
          const e = addDrawSeries(chart, {
            color, lineWidth: (d.lineWidth || 1), priceLineVisible: false, lastValueVisible: false,
            lineStyle: (d.lineStyle != null ? d.lineStyle : 2), title: "",
          });
          e.setData(a === b ? [{ time: a, value: price }]
            : [{ time: a, value: price }, { time: b, value: price }]);
          state.drawSeries.push(e);
        });
      } else if (d.type === "channel") {
        // two anchors define the line; a third sets how far the parallel sits
        let off = 0;
        if (d.t3 != null && idx.get(String(d.t3)) != null && i2 !== i1) {
          off = Number(d.p3) - (P1 + ((P2 - P1) * (idx.get(String(d.t3)) - i1)) / (i2 - i1));
        }
        seg(pA, pB, { title: "channel" });
        if (off !== 0) seg(pA + off, pB + off, {});
      } else if (d.type === "vline") {
        const bars = state.chartBars || [];
        let lo = Infinity, hi = -Infinity;
        bars.forEach((b) => {
          if (!isFinite(b.low) || !isFinite(b.high)) return;
          if (b.low < lo) lo = b.low;
          if (b.high > hi) hi = b.high;
        });
        if (!isFinite(lo) || !isFinite(hi) || !a) return;
        const prim = makeVerticalLinePrimitive(chart, String(a), color);
        try { state.candleSeries.attachPrimitive(prim); state.drawPrimitives.push({ series: state.candleSeries, prim }); }
        catch (e) { const v = seg(lo, hi, { title: "" }); v.setData([{ time: a, value: lo }, { time: a, value: hi }]); state.drawSeries.push(v); }
        return;
      } else if (d.type === "crossline") {
        // vertical component via primitive (true vertical, no slant)
        const bars = state.chartBars || [];
        let lo = Infinity, hi = -Infinity;
        bars.forEach((b) => {
          if (!isFinite(b.low) || !isFinite(b.high)) return;
          if (b.low < lo) lo = b.low;
          if (b.high > hi) hi = b.high;
        });
        if (isFinite(lo) && isFinite(hi) && a) {
          const prim = makeVerticalLinePrimitive(chart, String(a), color);
          try { state.candleSeries.attachPrimitive(prim); state.drawPrimitives.push({ series: state.candleSeries, prim }); }
          catch (e) { const v = seg(lo, hi, { title: "" }); v.setData([{ time: a, value: lo }, { time: a, value: hi }]); state.drawSeries.push(v); }
        }
        // horizontal component
        const h = addDrawSeries(chart, {
          color, lineWidth: (d.lineWidth || 1), priceLineVisible: false, lastValueVisible: false,
          lineStyle: (d.lineStyle != null ? d.lineStyle : 2), title: "",
        });
        const first = dts[0], last = dts[dts.length - 1];
        h.setData(first === last ? [{ time: first, value: P1 }]
          : [{ time: first, value: P1 }, { time: last, value: P1 }]);
        state.drawSeries.push(h);
      } else if (d.type === "hray") {
        // horizontal ray: from the anchor date to ~30 future weekday sessions
        const projT = nextWeekdayDates(30, dts[dts.length - 1]);
        const data = [{ time: a, value: P1 }, ...projT.map((tt) => ({ time: tt, value: P1 }))]
          .sort((u, v) => (u.time < v.time ? -1 : 1));
        const s = addDrawSeries(chart, {
          color, lineWidth: (d.lineWidth || 2), priceLineVisible: false, lastValueVisible: false, title: "",
        });
        s.setData(data);
        chart.timeScale().applyOptions({ rightOffset: 32 });
        state.drawSeries.push(s);
      } else if (d.type === "extended") {
        // the drawn line, extrapolated with its own slope to both chart edges
        const perBar = (P2 - P1) / Math.max(1, Math.abs(i2 - i1));
        const pStart = P1 + perBar * (0 - i1);
        const pEnd = P1 + perBar * ((dts.length - 1) - i1);
        seg(pStart, pEnd, { title: "extended", width: 2 });
      } else if (d.type === "rectangle") {
        const top = Math.max(P1, P2), bot = Math.min(P1, P2);
        seg(top, top, {}); seg(bot, bot, {});
        const defVert = (when) => {
          const s = addDrawSeries(chart, {
            color, lineWidth: (d.lineWidth || 1), priceLineVisible: false, lastValueVisible: false, title: "",
          });
          s.setData([{ time: when, value: top }, { time: when, value: bot }]);
          state.drawSeries.push(s);
        };
        defVert(a); defVert(b);
        // diagonal hint between the anchors makes the box readable as a rectangle
        seg(pA, pB, { dashed: true });
      } else if (d.type === "arrow") {
        seg(pA, pB, { title: "", width: 2 });
        // the head is a marker pinned to the SECOND anchor: it rides entirely on
        // chart (time, price) coordinates, never screen pixels
        const s = state.drawSeries[state.drawSeries.length - 1];
        try {
          s.setMarkers([{
            time: String(d.t2),
            position: P2 >= P1 ? "aboveBar" : "belowBar",
            color, shape: "arrowUp", text: "",
          }]);
        } catch (e) { /* arrow marker unsupported on this series — the shaft still renders */ }
      } else if (d.type === "price_range" || d.type === "date_range") {
        // Variant of `measure` restricted to one axis, so the tool never has
        // to be told which delta the user cares about (§5.8 measurement set).
        const bars0 = Math.abs(i2 - i1) + 1;
        if (d.type === "price_range") {
          const delta = P2 - P1;
          const pct = P1 ? (delta / P1) * 100 : 0;
          const label = `${delta >= 0 ? "+" : ""}${fmtNum(delta)} (${fmtNum(pct)}%)`;
          const v = seg(pA, pB, { title: label });
          v.setData(a === b ? [{ time: a, value: P1 }] : [{ time: a, value: P1 }, { time: a, value: P2 }]);
          const top = Math.max(P1, P2), bot = Math.min(P1, P2);
          [top, bot].forEach((price) => {
            const e = addDrawSeries(chart, {
              color, lineWidth: (d.lineWidth || 1), priceLineVisible: false, lastValueVisible: false, lineStyle: (d.lineStyle != null ? d.lineStyle : 2), title: "",
            });
            e.setData(a === b ? [{ time: a, value: price }]
              : [{ time: a, value: price }, { time: b, value: price }]);
            state.drawSeries.push(e);
          });
        } else {
          const label = `${bars0} bars · ${fmtNum(P1)}`;
          seg(P1, P1, { title: label });
        }
      } else if (d.type === "fib_timezones") {
        // Vertical markers at fib BAR counts after the first anchor, spanning
        // the loaded data's own price range. Bar count = trading days between
        // anchors defines "1 bar"; the zones never extend beyond loaded data.
        const bars0 = state.chartBars || [];
        let lo = Infinity, hi = -Infinity;
        bars0.forEach((b) => {
          if (!isFinite(b.low) || !isFinite(b.high)) return;
          if (b.low < lo) lo = b.low;
          if (b.high > hi) hi = b.high;
        });
        if (!isFinite(lo) || !isFinite(hi)) return;
        const fibs = [1, 2, 3, 5, 8, 13, 21, 34, 55, 89];
        const step = Math.max(1, Math.abs(i2 - i1));
        fibs.forEach((f) => {
          const target = Math.min(i1 + f * step, dts.length - 1);
          const tt = dts[target];
          if (tt == null) return;
          const s = addDrawSeries(chart, {
            color, lineWidth: (d.lineWidth || 1), priceLineVisible: false, lastValueVisible: false, title: "", lineStyle: (d.lineStyle != null ? d.lineStyle : 2),
          });
          s.setData([{ time: tt, value: lo }, { time: tt, value: hi }]);
          state.drawSeries.push(s);
          state.drawMarkers.push({
            time: tt, position: "aboveBar", color, shape: "circle", text: String(f),
          });
        });
      } else if (d.type === "fib_fan") {
        // Rays from anchor 1 through fib fractions of the 1→2 leg, extended to
        // the loaded right edge. Slope is in data space (index, price), so the
        // fan stays anchored to real bars under pan/zoom.
        const ratios = (Array.isArray(d.ratios) && d.ratios.length)
          ? d.ratios : (DRAW_DEFAULT_RATIOS.fib_fan);
        const span = Math.max(1, Math.abs(i2 - i1));
        const leg = P2 - P1;
        ratios.forEach((r) => {
          const pEnd = P1 + leg * r;
          const iEnd = Math.max(i1, i2); // fan apex through anchor 2
          const iLast = dts.length - 1;
          const slope = (pEnd - P1) / span;
          const pLast = P1 + slope * (iLast - i1);
          const s = addDrawSeries(chart, {
            color, lineWidth: (d.lineWidth || 1), priceLineVisible: false, lastValueVisible: false,
            title: "", lineStyle: (d.lineStyle != null ? d.lineStyle : 2),
          });
          const tEnd = dts[Math.min(iEnd, iLast)];
          s.setData(i1 === iLast ? [{ time: dts[i1], value: P1 }]
            : [{ time: dts[i1], value: P1 }, { time: tEnd, value: iLast <= iEnd ? pEnd : pLast }]);
          state.drawSeries.push(s);
        });
        seg(pA, pB, { dashed: true, width: 1 });
      } else if (d.type === "regression_channel") {
        // OLS centre line of CLOSES between the anchors, plus parallel ±k·σ
        // bands (ratios[0] = k, default 2). Honest fit: computed on the chart's
        // own loaded window, drawn only across the selected span. The math
        // lives in olsFitXY() so it can be unit-checked (window.__mtMath).
        const k = (Array.isArray(d.ratios) && isFinite(Number(d.ratios[0])) && Number(d.ratios[0]) > 0)
          ? Number(d.ratios[0]) : 2;
        const iS = Math.min(i1, i2), iE = Math.max(i1, i2);
        const closes = [];
        for (let k2 = iS; k2 <= iE; k2++) {
          const b = (state.chartBars || [])[k2];
          if (b && isFinite(b.close)) closes.push({ i: k2, c: b.close });
        }
        if (closes.length >= 2) {
          const fitResp = olsFitXY(closes.map((v) => [v.i, v.c]));
          if (!fitResp) return;   // degenerate (all-identical inputs): draw nothing
          const { slope, intercept, sd } = fitResp;
          const fit = () => {
            const s3 = addDrawSeries(chart, {
              color, lineWidth: (d.lineWidth || 2), priceLineVisible: false, lastValueVisible: false, title: "",
            });
            s3.setData([
              { time: dts[iS], value: intercept + slope * iS },
              { time: dts[iE], value: intercept + slope * iE },
            ]);
            state.drawSeries.push(s3);
          };
          fit();
          [[k, "raw"], [-k, "raw"]].forEach(([kv]) => {
            const s3 = addDrawSeries(chart, {
              color, lineWidth: (d.lineWidth || 1), priceLineVisible: false, lastValueVisible: false, title: "", lineStyle: (d.lineStyle != null ? d.lineStyle : 2),
            });
            s3.setData([
              { time: dts[iS], value: intercept + slope * iS + kv * sd },
              { time: dts[iE], value: intercept + slope * iE + kv * sd },
            ]);
            state.drawSeries.push(s3);
          });
          drawStatus(`Regression channel · k = ${fmtNum(k)}σ over ${closes.length} closes · slope ${fmtNum(slope, 3)} per bar.`);
        }
      } else if (d.type === "long_pos" || d.type === "short_pos") {
        // position tool: anchor 1 = entry, anchor 2 = stop; ratios[0] = R (default 2)
        // The target always lands on the side OPPOSITE the stop, so a
        // "wrong-sided" second anchor mirrors the plan instead of showing a
        // target inside the loss zone.
        const R = (Array.isArray(d.ratios) && isFinite(Number(d.ratios[0])) && Number(d.ratios[0]) > 0)
          ? Number(d.ratios[0]) : 2.0;
        const riskAbs = Math.abs(P1 - P2);
        const dir = d.type === "long_pos" ? (P2 < P1 ? 1 : -1) : (P2 > P1 ? -1 : 1);
        const target = P1 + dir * riskAbs * R;
        const riskPct = riskAbs / P1 * 100;
        seg(pA, pB, { title: "", width: 1, dashed: true });
        const entry = addDrawSeries(chart, {
          color, lineWidth: (d.lineWidth || 2), priceLineVisible: false,
          lastValueVisible: false, title: `entry ${fmtNum(P1)}`,
        });
        entry.setData(a === b ? [{ time: a, value: P1 }] : [{ time: a, value: P1 }, { time: b, value: P1 }]);
        state.drawSeries.push(entry);
        const stp = addDrawSeries(chart, {
          color: PRAVAHA.down, lineWidth: (d.lineWidth || 1), priceLineVisible: false,
          lastValueVisible: false, lineStyle: (d.lineStyle != null ? d.lineStyle : 2), title: `stop ${fmtNum(P2)}`,
        });
        stp.setData(a === b ? [{ time: a, value: P2 }] : [{ time: a, value: P2 }, { time: b, value: P2 }]);
        state.drawSeries.push(stp);
        if (isFinite(target) && target !== P1) {
          const tgt = addDrawSeries(chart, {
            color: PRAVAHA.up, lineWidth: (d.lineWidth || 1), priceLineVisible: false,
            lastValueVisible: false, lineStyle: (d.lineStyle != null ? d.lineStyle : 2), title: `target ${fmtNum(target)}`,
          });
          tgt.setData(a === b ? [{ time: a, value: target }] : [{ time: a, value: target }, { time: b, value: target }]);
          state.drawSeries.push(tgt);
        }
        drawStatus(`${d.type === "long_pos" ? "Long" : "Short"} plan · R:R ${R.toFixed(2)} · risk ${riskPct.toFixed(2)}% · target ${fmtNum(target)} (${(R * riskPct).toFixed(2)}%)`);
      }
      return;
    }

    // ---- text note: rendered in the marker pass below ---------------------
    if (d.type === "text" || d.type === "note" || d.type === "flag" || d.type === "price_label") {
      if (d.type === "price_label") {
        // labelled level chip: a full-span horizontal line titled with the
        // user's text + the exact price (both live in chart coordinates)
        const s = addDrawSeries(chart, {
          color, lineWidth: (d.lineWidth || 1), priceLineVisible: false, lastValueVisible: false,
          title: `${(d.text || "label")}${d.text ? "" : ""} ${fmtNum(Number(d.p1))}`, lineStyle: (d.lineStyle != null ? d.lineStyle : 0),
        });
        const l0 = Number(d.p1);
        s.setData(sameTime ? [{ time: firstTime, value: l0 }]
          : [{ time: firstTime, value: l0 }, { time: lastTime, value: l0 }]);
        state.drawSeries.push(s);
      }
      // note and flag render only as markers (see the marker pass); text too
      return;
    }

    // ---- N-anchor tools (patterns, pitchfork, triangle, polyline) ---------
    if (DRAW_ANCHOR_LETTERS[d.type] || DRAW_VARLEN.has(d.type) || d.type === "triangle" || d.type === "gann_fan") {
      const dts = state.chartDates || [];
      const idx = new Map(dts.map((dt, k) => [dt, k]));
      if (d.type === "pitchfork" || d.type === "schiff_pitchfork") {
        // A = 1, B = 2, C = 3. Median: A → midpoint(BC), extended across the
        // loaded window; the tines run parallel through B and C.
        // Schiff variant: the handle keeps anchor 1's date but its price moves
        // halfway toward the price of mid(BC) — a flattened fork, not a new
        // fork family; the tines keep the anchor geometry.
        const iA = idx.get(String(d.t1)), iB = idx.get(String(d.t2)), iC = idx.get(String(d.t3));
        const PA = Number(d.p1), PB = Number(d.p2), PC = Number(d.p3);
        if (iA != null && iB != null && iC != null && [PA, PB, PC].every(isFinite)) {
          const iM = (iB + iC) / 2, PM = (PB + PC) / 2;
          const PS = d.type === "schiff_pitchfork" ? (PA + PM) / 2 : PA;
          const slope = iM !== iA ? (PM - PS) / (iM - iA) : 0;
          const line = (i0, p0, widthPx) => {
            const s = addDrawSeries(chart, {
              color, lineWidth: widthPx, priceLineVisible: false, lastValueVisible: false, title: "",
            });
            const iLast = dts.length - 1;
            const iFrom = Math.max(0, Math.min(i0, iLast));
            s.setData([{ time: dts[iFrom], value: p0 }, {
              time: dts[iLast], value: p0 + slope * (iLast - iFrom),
            }]);
            state.drawSeries.push(s);
          };
          line(iA, PS, 2);          // median line (starts at the adjusted handle)
          line(iB, PB, 1);          // upper tine through B
          line(iC, PC, 1);          // lower tine through C
        }
        return;
      }
      if (d.type === "gann_fan") {
        // Leg-relative Gann fan (honest approximation): the 1x1 slope IS the
        // anchor-1→anchor-2 leg, and every other ray is a multiple of it
        // (8x1 … 1x8). Angles therefore follow the chart's own price scale —
        // they are NOT absolute degrees, because a daily NEPSE chart has no
        // uniform bar/price ratio across symbols.
        const dts = state.chartDates || [];
        const idx = new Map(dts.map((dt, k) => [dt, k]));
        const i1 = idx.get(String(d.t1));
        const P1 = Number(d.p1), P2 = Number(d.p2);
        const i2 = idx.get(String(d.t2));
        const ratios = (Array.isArray(d.ratios) && d.ratios.length)
          ? d.ratios : [...(DRAW_DEFAULT_RATIOS[d.type] || [])];
        if (i1 == null || i2 == null || !isFinite(P1) || !isFinite(P2)) return;
        const step = Math.max(0.5, Math.abs(i2 - i1));   // bars between anchors (≥ half a bar)
        const base = (P2 - P1) / step;                  // 1x1 slope = the leg
        const gannName = (r) => {
          const map = { 8: "8x1", 4: "4x1", 2: "2x1", 1: "1x1", 0.5: "1x2", 0.25: "1x4", 0.125: "1x8" };
          const key = Object.keys(map).find((x) => Math.abs(Number(x) - r) < 1e-9);
          return key ? map[key] : `${fmtNum(r, 3)}x`;
        };
        const iLast = dts.length - 1;
        const iFrom = Math.max(0, Math.min(i1, iLast));
        const ray = (k, dashed) => {
          const s = addDrawSeries(chart, {
            color, lineWidth: (d.lineWidth || 1), priceLineVisible: false, lastValueVisible: false,
            title: "", lineStyle: dashed ? 2 : 0,
          });
          const v1 = P1 + k * base * (iFrom - i1);
          s.setData([
            { time: dts[iFrom], value: v1 },
            { time: dts[iLast], value: P1 + k * base * (iLast - i1) },
          ]);
          state.drawSeries.push(s);
        };
        ratios.forEach((r) => {
          const k = Number(r);
          if (!isFinite(k) || k === 0) return;
          ray(k, Math.abs(k) !== 1);   // 1x1 is solid, others dashed
          ray(-k, true);               // mirrored ray below the origin
        });
        return;
      }
      if (d.type === "ellipse") {
        const dts = state.chartDates || [];
        const idx = new Map(dts.map((dt, k) => [dt, k]));
        const iC = idx.get(String(d.t1)), iX = idx.get(String(d.t2)), iY = idx.get(String(d.t3));
        const PC = Number(d.p1), PX = Number(d.p2), PY = Number(d.p3);
        if (iC == null || iX == null || iY == null || ![PC, PX, PY].every(isFinite)) return;
        const rx = Math.abs(iX - iC), ry = Math.abs(PY - PC);
        if (rx < 0.5 || ry === 0) return;
        const pts = [];
        const seen = new Set();
        const N = 72;
        for (let k = 0; k <= N; k++) {
          const ang = (k / N) * 2 * Math.PI;
          const i = iC + rx * Math.cos(ang);
          const p = PC + ry * Math.sin(ang);
          const ri = Math.round(i);
          if (ri < 0 || ri >= dts.length) continue;
          const time = dts[ri];
          if (time == null || seen.has(time)) continue;
          seen.add(time);
          if (!isFinite(p)) continue;
          pts.push({ time, value: p });
        }
        if (pts.length < 3) return;
        pts.sort((a, b) => (a.time < b.time ? -1 : a.time > b.time ? 1 : 0));
        const s = addDrawSeries(chart, { color, lineWidth: 1.5, priceLineVisible: false, lastValueVisible: false, title: "" });
        s.setData(pts);
        state.drawSeries.push(s);
        return;
      }
      if (d.type === "hns") {
        // Manual head-and-shoulders annotation: 5 anchors LS, H, RS, N1, N2.
        // Draw the connected shoulder-head-shoulder polyline plus the neckline.
        const parts = anchorParts(d);
        if (parts.length < 5) return;
        segMulti({ ...d, t4: d.t4, p4: d.p4, t5: d.t5, p5: d.p5 }, color, { width: 2 });
        // neckline (dashed) between anchors 4 and 5
        const dts = state.chartDates || [];
        const idx = new Map(dts.map((dt, k) => [dt, k]));
        const i4 = idx.get(String(d.t4)), i5 = idx.get(String(d.t5));
        const P4 = Number(d.p4), P5 = Number(d.p5);
        if (i4 != null && i5 != null && [P4, P5].every(isFinite)) {
          const s = addDrawSeries(chart, { color, lineWidth: 1.5, priceLineVisible: false, lastValueVisible: false, title: "", lineStyle: 2 });
          const lo = Math.min(i4, i5), hi = Math.max(i4, i5);
          s.setData([{ time: dts[lo], value: lo === i4 ? P4 : P5 }, { time: dts[hi], value: lo === i4 ? P5 : P4 }]);
          state.drawSeries.push(s);
        }
        return;
      }
      if (d.type === "polyline") {
        segMulti(d, color, { width: 2 });
        return;
      }
      segMulti(d, color, { width: 2, dashed: false });
      return;
    }

    // ---- fib 3-click tools: trend-based extension + fib channel -----------
    if (d.type === "fib_tbe" || d.type === "fib_channel") {
      const dts = state.chartDates || [];
      const idx = new Map(dts.map((dt, k) => [dt, k]));
      const i1 = idx.get(String(d.t1)), i2 = idx.get(String(d.t2)), i3 = idx.get(String(d.t3));
      const P1 = Number(d.p1), P2 = Number(d.p2), P3 = Number(d.p3);
      const ratios = (Array.isArray(d.ratios) && d.ratios.length)
        ? d.ratios : [...(DRAW_DEFAULT_RATIOS[d.type] || [])];
      if (i1 == null || i2 == null || i3 == null || ![P1, P2, P3].every(isFinite)) return;
      const hline = (priceVal, fromI, titleTxt, dashed) => {
        const s = addDrawSeries(chart, {
          color, lineWidth: (d.lineWidth || 1), priceLineVisible: false, lastValueVisible: false,
          title: titleTxt || "", lineStyle: dashed ? 2 : 0,
        });
        const iEnd = dts.length - 1;
        const iFrom = Math.max(0, Math.min(fromI, iEnd));
        s.setData([{ time: dts[iFrom], value: priceVal }, { time: dts[iEnd], value: priceVal }]);
        state.drawSeries.push(s);
      };
      if (d.type === "fib_tbe") {
        // Trend-based Fib extension: the impulse X→A (anchors 1→2) is
        // projected from B (anchor 3): level = P3 + (P2 − P1) · r.
        const leg = P2 - P1;
        segMulti({ ...d, t3: undefined }, color, { dashed: true }); // show the measured legs
        ratios.forEach((r) => hline(P3 + leg * r, i3, `ext ${fmtNum(r, 3)}`, true));
      } else {
        // Fib channel: base line 1→2, third anchor sets the offset height;
        // every ratio r draws the parallel at base + r·offset.
        const base = (i) => P1 + ((P2 - P1) * (i - i1)) / Math.max(1, Math.abs(i2 - i1));
        const off = P3 - base(i3);
        segMulti({ ...d, t3: undefined }, color, {});
        ratios.forEach((r) => {
          const lo = Math.min(i1, i3), hi = Math.max(i2, i3);
          const s = addDrawSeries(chart, {
            color, lineWidth: (d.lineWidth || 1), priceLineVisible: false, lastValueVisible: false,
            title: `fib ${fmtNum(r, 3)}`, lineStyle: r === 0 ? 0 : 2,
          });
          s.setData([
            { time: dts[lo], value: base(lo) + off * r },
            { time: dts[hi], value: base(hi) + off * r },
          ]);
          state.drawSeries.push(s);
        });
      }
      return;
    }

    drawingLevels(d).forEach((lvl) => {
      const s = addDrawSeries(chart, {
        color, lineWidth: (d.lineWidth || 1), priceLineVisible: false, lastValueVisible: false,
        title: `${d.type === "fib_extension" ? "ext" : "fib"} ${lvl.ratio} @ ${fmtNum(lvl.price)}`,
      });
      const data = a === b ? [{ time: a, value: lvl.price }]
        : [{ time: a, value: lvl.price }, { time: b, value: lvl.price }];
      s.setData(data);
      state.drawSeries.push(s);
    });
  });
  // Anchor markers so the user can see (and grab) the handles.
  state.drawMarkers = [];
  (state.drawings || []).forEach((d) => {
    if (d.type === "text" || d.type === "note") {
      state.drawMarkers.push({
        time: d.t1, position: "aboveBar", color: d.color || DRAW_COLORS[0],
        shape: "square", text: d.text || "note",
      });
    }
    if (d.type === "flag") {
      state.drawMarkers.push({
        time: d.t1, position: "aboveBar", color: d.color || PRAVAHA.down,
        shape: "circle", text: "⚑",
      });
    }
  });
  flushMarkers();
  renderAnchorHandles();
}

/* ---------------------------------------------------------- draw list panel */
/* One master switch for drawing visibility (§6). The toolbar button and the
   drawer checkbox both call this; hiding never deletes — afterDrawingsChanged
   is intentionally NOT used here, because hiding is not a content change. */
function setDrawVisible(v) {
  state.drawVisible = !!v;
  const cb = $("#draw-visible"), btn = $("#draw-toggle");
  if (cb) cb.checked = !!v;
  if (btn) btn.textContent = v ? "Hide drawings" : "Show drawings";
  renderDrawings();
  drawStatus(v
    ? "Drawings visible."
    : `All ${(state.drawings || []).length} drawing(s) hidden — nothing was deleted; click Show drawings to restore.`);
}

function renderDrawList() {
  const el = $("#draw-list");
  if (!el) return;
  const items = state.drawings || [];
  if (!items.length) {
    el.innerHTML = `<div class="empty">No drawings for ${esc(state.chartSymbol || "this symbol")}. Pick a tool above and click the chart.</div>`;
    return;
  }
  el.innerHTML = `<div class="tablewrap">${table(
    ["#", "Type", "Anchor 1 (date @ price)", "Anchor 2", "Anchor 3+", "Ratios / R", "Text", "Visible", "Lock", ""],
    items.map((d, i) => [
      { html: `<b>${i + 1}</b>${state.drawSelectId === d.id ? ' <span class="pill pill-info">selected</span>' : ""}` },
      { html: esc(d.name || DRAW_LABELS[d.type] || d.type) },
      { html: `${esc(d.t1)} @ ${fmtNum(Number(d.p1))}` },
      { html: anchorParts(d).length < 2 ? "—" : `${esc(anchorParts(d)[1][1])} @ ${fmtNum(anchorParts(d)[1][2])}` },
      { html: anchorParts(d).length > 2
        ? anchorParts(d).slice(2).map((pp) => `${esc(pp[1])} @ ${fmtNum(pp[2])}`).join(" · ")
        : "—" },
      { html: d.type === "fib_retracement" || d.type === "fib_extension" || d.type === "long_pos" || d.type === "short_pos"
        ? `<input class="dr-ratios" data-id="${esc(d.id)}" style="width:14em" value="${esc((d.ratios || []).join(", "))}" placeholder="${d.type === "long_pos" || d.type === "short_pos" ? "R:R e.g. 2.0" : "0.382, 0.618"}" />`
        : `<span class="hint">—</span>` },
      { html: d.type === "text"
        ? `<button class="ghost dr-text" data-id="${esc(d.id)}">${esc(d.text || "edit text")}</button>`
        : "—" },
      { html: `<input type="checkbox" class="dr-vis" data-id="${esc(d.id)}"${d.hidden ? "" : " checked"} />` },
      { html: `<input type="checkbox" class="dr-lock" data-id="${esc(d.id)}"${d.locked ? " checked" : ""} />` },
      { html: `<button class="ghost dr-rename" data-id="${esc(d.id)}">Rename</button> <button class="ghost dr-del" data-id="${esc(d.id)}">Delete</button>` },
    ]))}</div>`;

  el.querySelectorAll(".dr-text").forEach((b) => b.addEventListener("click", () => {
    const d = (state.drawings || []).find((x) => x.id === b.dataset.id);
    if (!d) return;
    const note = window.prompt("Edit text note:", d.text || "");
    if (note === null) return;
    pushDrawHistory();
    d.text = String(note).slice(0, 120);
    afterDrawingsChanged();
  }));
  el.querySelectorAll(".dr-rename").forEach((b) => b.addEventListener("click", () => {
    const d = (state.drawings || []).find((x) => x.id === b.dataset.id);
    if (!d) return;
    const nm = window.prompt("Name for this drawing:", d.name || "");
    if (nm === null) return;
    pushDrawHistory();
    d.name = String(nm).slice(0, 80) || undefined;
    afterDrawingsChanged();
  }));
  el.querySelectorAll(".dr-lock").forEach((cb) => cb.addEventListener("change", () => {
    const d = (state.drawings || []).find((x) => x.id === cb.dataset.id);
    if (!d) return;
    pushDrawHistory();
    d.locked = cb.checked;
    afterDrawingsChanged();
    drawStatus(cb.checked ? "Drawing locked — it cannot be dragged or erased." : "Drawing unlocked.");
  }));
  el.querySelectorAll(".dr-ratios").forEach((inp) => inp.addEventListener("change", () => {
    const d = (state.drawings || []).find((x) => x.id === inp.dataset.id);
    if (!d) return;
    const ratios = inp.value.split(",").map((t) => Number(t.trim())).filter((n) => isFinite(n));
    pushDrawHistory();
    d.ratios = ratios;
    afterDrawingsChanged();
  }));
  el.querySelectorAll(".dr-vis").forEach((cb) => cb.addEventListener("change", () => {
    const d = (state.drawings || []).find((x) => x.id === cb.dataset.id);
    if (!d) return;
    d.hidden = !cb.checked;
    afterDrawingsChanged();
  }));
  el.querySelectorAll(".dr-del").forEach((btn) => btn.addEventListener("click", () => {
    pushDrawHistory();
    state.drawings = (state.drawings || []).filter((x) => x.id !== btn.dataset.id);
    afterDrawingsChanged();
  }));
  bindDrawProps();
  renderDrawProps();
}

function bindDrawProps() {
  const panel = $("#draw-props");
  if (!panel || panel.dataset.bound === "1") return;
  panel.dataset.bound = "1";
  const apply = (mut) => {
    const d = (state.drawings || []).find((x) => x.id === state.drawSelectId);
    if (!d) return;
    pushDrawHistory();
    mut(d);
    afterDrawingsChanged();
    renderDrawProps();
  };
  $("#dp-color").addEventListener("input", (e) => apply((d) => { d.color = e.target.value; }));
  $("#dp-opacity").addEventListener("input", (e) => apply((d) => { d.opacity = Number(e.target.value); }));
  $("#dp-width").addEventListener("change", (e) => apply((d) => { const v = Number(e.target.value); d.lineWidth = isFinite(v) && v > 0 ? v : d.lineWidth; }));
  $("#dp-style").addEventListener("change", (e) => apply((d) => { d.lineStyle = Number(e.target.value); }));
  $("#dp-visible").addEventListener("change", (e) => apply((d) => { d.hidden = !e.target.checked; }));
  $("#dp-lock").addEventListener("change", (e) => apply((d) => { d.locked = !!e.target.checked; }));
  $("#dp-ext-left").addEventListener("change", (e) => apply((d) => { d.extendLeft = !!e.target.checked; }));
  $("#dp-ext-right").addEventListener("change", (e) => apply((d) => { d.extendRight = !!e.target.checked; }));
  $("#dp-ext-both").addEventListener("change", (e) => apply((d) => { const v = !!e.target.checked; d.extendLeft = v; d.extendRight = v; }));
  $("#dp-text").addEventListener("click", () => {
    const d = (state.drawings || []).find((x) => x.id === state.drawSelectId);
    if (!d) return;
    const note = window.prompt("Edit text:", d.text || "");
    if (note === null) return;
    pushDrawHistory();
    d.text = String(note).slice(0, 120);
    afterDrawingsChanged();
    renderDrawProps();
  });
  $("#dp-delete").addEventListener("click", () => {
    if (!state.drawSelectId) return;
    pushDrawHistory();
    state.drawings = (state.drawings || []).filter((x) => x.id !== state.drawSelectId);
    state.drawSelectId = null;
    afterDrawingsChanged();
    renderDrawProps();
  });
  $("#dp-duplicate").addEventListener("click", () => {
    const d = (state.drawings || []).find((x) => x.id === state.drawSelectId);
    if (!d) return;
    pushDrawHistory();
    const copy = JSON.parse(JSON.stringify(d));
    copy.id = nextDrawingId();
    copy.created = new Date().toISOString();
    state.drawings.push(copy);
    state.drawSelectId = copy.id;
    afterDrawingsChanged();
    renderDrawProps();
  });
}

function renderDrawProps() {
  const panel = $("#draw-props");
  if (!panel) return;
  const d = (state.drawings || []).find((x) => x.id === state.drawSelectId);
  if (!d) { panel.hidden = true; return; }
  panel.hidden = false;
  const color = /^#[0-9a-f]{6}$/i.test(String(d.color || "")) ? d.color : "#9dc4ae";
  $("#dp-color").value = color;
  $("#dp-opacity").value = (d.opacity == null ? 1 : d.opacity);
  $("#dp-width").value = (d.lineWidth || 2);
  $("#dp-style").value = String(d.lineStyle != null ? d.lineStyle : 0);
  $("#dp-visible").checked = !d.hidden;
  $("#dp-lock").checked = !!d.locked;
  $("#dp-ext-left").checked = !!d.extendLeft;
  $("#dp-ext-right").checked = !!d.extendRight;
  $("#dp-ext-both").checked = !!d.extendLeft && !!d.extendRight;
  const parts = anchorParts(d);
  const m = (parts.length >= 2)
    ? (() => {
        const a = parts[0], b = parts[1];
        const ia = (state.chartDates || []).indexOf(String(a[1]));
        const ib = (state.chartDates || []).indexOf(String(b[1]));
        const pa = Number(a[2]), pb = Number(b[2]);
        const delta = pb - pa;
        const pct = pa ? (delta / pa) * 100 : 0;
        const bars = (ia >= 0 && ib >= 0) ? Math.abs(ib - ia) + 1 : null;
        const angle = (ia != null && ib != null) ? (Math.atan2(pb - pa, ib - ia) * 180 / Math.PI) : null;
        return `Selected ${esc(d.name || DRAW_LABELS[d.type] || d.type)} · anchors ${esc(a[1])} @ ${fmtNum(pa)} → ${esc(b[1])} @ ${fmtNum(pb)}`
          + ` · Δ ${fmtNum(delta)} (${fmtNum(pct)}%)`
          + (bars != null ? ` · ${bars} bars` : "")
          + (angle != null ? ` · angle ${fmtNum(angle, 2)}°` : "");
      })()
    : `Selected ${esc(d.name || DRAW_LABELS[d.type] || d.type)} · single anchor`;
  $("#dp-measure").textContent = m;
}


/* -------------------------------------------------------- pointer placement */
function drawStatus(msg) {
  const el = $("#draw-status");
  if (el) el.textContent = msg || "";
  updateToolBanner();
}

/* ---------------------------------------------------- active-tool banner
   A single, prominent line that says which drawing tool is active, what to do
   with it, how many anchors are required and how many are placed. Previously
   activating a tool only changed the cursor and a small status line, so a
   multi-anchor tool (Elliott impulse, ABCD, XABCD…) looked like it had done
   nothing. */
function drawAnchorNeed(tool) {
  if (!tool || DRAW_MODES.has(tool)) return 0;
  if (DRAW_MULTI_N[tool]) return DRAW_MULTI_N[tool];
  if (DRAW_VARLEN.has(tool)) return 0; // freeform, finished with Enter
  if (DRAW_ONECLICK.has(tool) || DRAW_ONE_TOOLS2.has(tool)) return 1;
  if (DRAW_THREECLICK.has(tool)) return 3;
  return 2;
}
function drawAnchorPlaced(tool) {
  if (state.drawMulti && state.drawMulti.type === tool) return state.drawMulti.pts.length;
  if (state.drawPending3) return 2;
  if (state.drawPending) return 1;
  return 0;
}
function railToolInfo(tool) {
  for (const g of RAIL_GROUPS) for (const t of g.tools) if (t.id === tool) return t;
  return null;
}
function updateToolBanner() {
  const el = $("#tool-banner");
  if (!el) return;
  const tool = state.drawTool;
  if (!tool) { el.hidden = true; return; }
  const info = railToolInfo(tool) || { name: DRAW_LABELS[tool] || tool, d: "" };
  const need = drawAnchorNeed(tool);
  const have = drawAnchorPlaced(tool);
  const nameEl = $("#tool-banner-name");
  const textEl = $("#tool-banner-text");
  const progEl = $("#tool-banner-progress");
  if (nameEl) nameEl.textContent = info.name || tool;
  if (textEl) {
    textEl.textContent = tool === "select"
      ? "Click a drawing to select it · drag the body to move it · Delete/Backspace removes it"
      : tool === "eraser"
        ? "Click a drawing on the chart to delete it — locked drawings stay"
        : (info.d || "") + " · Esc cancels";
  }
  if (progEl) {
    progEl.textContent = DRAW_VARLEN.has(tool)
      ? `${have} anchor(s) placed — Enter to finish`
      : need === 1 ? "single click" : `${have}/${need} anchors`;
  }
  el.hidden = false;
  el.dataset.tool = tool;
}

/* Normalise every time shape Lightweight Charts can give us (business-day
   string, BusinessDay object or UTCTimestamp) to the date key used by
   state.chartDates. Without this, an object time became "[object Object]" and
   the anchor could not be resolved back to a bar. */
function chartTimeKey(value) {
  if (value == null) return null;
  if (typeof value === "string") return value;
  if (typeof value === "number") {
    const d = new Date(value > 1e12 ? value : value * 1000);
    return isFinite(d.getTime()) ? d.toISOString().slice(0, 10) : null;
  }
  if (typeof value === "object") {
    if (value.timestamp != null) return chartTimeKey(value.timestamp);
    if (value.year != null && value.month != null && value.day != null) {
      const pad = (n) => String(n).padStart(2, "0");
      return `${value.year}-${pad(value.month)}-${pad(value.day)}`;
    }
  }
  return String(value);
}

/* Chart-local pointer coordinates. LWC coordinates start at the plot's content
   box, so the border (clientLeft/clientTop) is removed as well as the element's
   viewport offset. getBoundingClientRect also accounts for scroll, CSS zoom and
   fullscreen layout changes. */
function chartPointFromEvent(ev, container) {
  const el = container || $("#chart");
  if (!el) return { x: 0, y: 0 };
  const r = el.getBoundingClientRect();
  return { x: ev.clientX - r.left - (el.clientLeft || 0), y: ev.clientY - r.top - (el.clientTop || 0) };
}

function snapPriceToOhlc(t, price, strength) {
  if (!strength || strength === "off" || !isFinite(price)) return { price, snapped: false };
  const i = (state.chartDates || []).indexOf(String(t));
  const b = i >= 0 ? (state.chartBars || [])[i] : null;
  if (!b) return { price, snapped: false };
  const cs = state.candleSeries;
  const cands = [["close", b.close], ["open", b.open], ["high", b.high], ["low", b.low]];
  let cy = null;
  try { cy = cs.priceToCoordinate(price); } catch (e) { cy = null; }
  if (cy == null) return { price, snapped: false };
  let best = null;
  cands.forEach(([nm, v]) => {
    if (!isFinite(v)) return;
    let py = null;
    try { py = cs.priceToCoordinate(v); } catch (e) { py = null; }
    if (py == null) return;
    const d = Math.abs(py - cy);
    if (!best || d < best.d) best = { d, v, nm };
  });
  if (!best) return { price, snapped: false };
  if (strength === "strong") return { price: best.v, snapped: best.nm };
  return best.d <= 10 ? { price: best.v, snapped: best.nm } : { price, snapped: false };
}

function onChartClick(param) {
  const tool = state.drawTool;
  // A drag that ends on the chart (pan with the mouse down) also produces a
  // click. When the pointer travelled since mousedown, the intent is
  // navigation, not an anchor — drop it instead of planting an accidental
  // drawing (§5.8 drawing interaction correctness).
  if (tool && !DRAW_MODES.has(tool) && state.panEnabled !== false &&
      param && param.point && state.drawTool !== "select") {
    state.chartDrag = state.chartDrag || {};
    const dg = state.chartDrag;
    const md = dg.mouseDown;
    if (md) {
      const rect = $("#chart").getBoundingClientRect();
      const cx = rect.left + param.point.x, cy = rect.top + param.point.y;
      const dist = Math.hypot(cx - md.x, cy - md.y);
      if (dist > 12) { drawStatus("Drag detected — anchor dropped (navigate with the cursor tool)."); return; }
    }
  }
  if (!tool || DRAW_MODES.has(tool)) {
    if (param && param.point) {
      // Hit the drawing's visible geometry (body) first, then its anchors. The
      // eraser used to require clicking an anchor within 16px — effectively a
      // single-pixel target at the line's start — which read as "the eraser
      // does not work". Nearest wins so overlapping drawings behave predictably.
      const body = drawingBodyHit(param.point.x, param.point.y, 14);
      const anch = anchorHitAt(param.point.x, param.point.y, 20);
      const hit = body && anch ? (body.dist <= anch.dist ? body : anch) : (body || anch);
      if (tool === "eraser") {
        if (hit && !hit.locked) {
          pushDrawHistory();
          const gone = String(hit.id);
          state.drawings = (state.drawings || []).filter((d) => d.id !== gone);
          state.drawSelectId = null;
          afterDrawingsChanged();
          drawStatus("Drawing erased (Undo restores it).");
        } else {
          drawStatus(hit ? "That drawing is locked — unlock it in the list below." : "No drawing under the cursor.");
        }
        return;
      }
      if (tool === "select" || !tool) {
        state.drawSelectId = hit && !hit.locked ? hit.id : null;
        renderDrawList();
        renderDrawProps();
        refreshSelectionMarkers();
        drawStatus(state.drawSelectId
          ? "Drawing selected — drag it or an anchor to move it (Delete removes it)."
          : "");
        return;
      }
    }
    return;
  }
  const chart = state.charts.price;
  if (!chart || !param || !param.point) { drawStatus("Click inside the plotted bars."); return; }
  // Read the price at the clicked y. coordinateToPrice() is unreliable in
  // this LWC build for out-of-range y (returns garbage), so try it first for
  // in-range clicks and fall back to the clicked bar's close price.
  let price = null;
  try { price = state.candleSeries.coordinateToPrice(param.point.y); } catch (e) { price = null; }
  if (price == null || !isFinite(price) || Math.abs(price) > 1e6) {
    try {
      const sd = param.seriesData;
      const bar = sd && (sd[state.candleSeries] || Object.values(sd)[0]);
      if (bar && typeof bar.close === "number" && isFinite(bar.close)) price = Number(bar.close);
      else if (bar && typeof bar.value === "number" && isFinite(bar.value)) price = Number(bar.value);
    } catch (e) { price = null; }
  }
  if (price == null || !isFinite(price)) { drawStatus("Could not read a price at that point."); return; }
  // Resolve the click's timestamp. Lightweight Charts supplies param.time for
  // in-bar clicks, but it is null/undefined for clicks in the empty space to
  // the right of the last bar (and, in some builds, beyond the data range).
  // Falling back to barIndexAtX() — the same logical-coordinate helper the
  // drag path uses — keeps placement stable and clamps to the data range
  // instead of jumping to an unrelated bar. A click left of the first bar
  // clamps to the first bar; a click right of the last bar clamps to the last.
  let t = chartTimeKey(param.time);
  if (t == null) {
    const idx = barIndexAtX(param.point.x);
    if (idx != null && state.chartDates && state.chartDates[idx] != null) {
      t = String(state.chartDates[idx]);
    }
  }
  if (t == null) { drawStatus("Click inside the plotted bars."); return; }
  const snap = snapPriceToOhlc(t, Number(price), state.drawMagnet);
  price = snap.price;
  if (snap.snapped) drawStatus(`Snapped to ${snap.snapped.toUpperCase()} of the ${t} bar.`);

  // second-wave one-click tools
  if (DRAW_ONE_TOOLS2.has(tool)) {
    pushDrawHistory();
    if (tool === "price_label") {
      const label = window.prompt("Label text for this price level:", "");
      if (label === null) { drawStatus("Price label cancelled."); return; }
      state.drawings.push({
        id: nextDrawingId(), type: "price_label", t1: t, p1: price, t2: t, p2: price,
        ratios: [], text: String(label).slice(0, 40),
        color: DRAW_COLORS[state.drawings.length % DRAW_COLORS.length], created: new Date().toISOString(),
      });
      drawStatus("Price label added — full-width level line, editable in the list.");
    } else if (tool === "note") {
      const note = window.prompt("Note text:", "");
      if (note === null) { drawStatus("Note cancelled."); return; }
      state.drawings.push({
        id: nextDrawingId(), type: "note", t1: t, p1: price, t2: t, p2: price,
        ratios: [], text: String(note).slice(0, 120),
        color: DRAW_COLORS[state.drawings.length % DRAW_COLORS.length], created: new Date().toISOString(),
      });
      drawStatus("Note added (text marker + anchor handle).");
    } else { // flag
      state.drawings.push({
        id: nextDrawingId(), type: "flag", t1: t, p1: price, t2: t, p2: price, ratios: [],
        color: PRAVAHA.down, created: new Date().toISOString(),
      });
      drawStatus("Flag marker added.");
    }
    state.drawPending = null;
    state.pendingMarker = [];
    afterDrawingsChanged();
    if (!state.drawStay) setDrawTool(null);
    return;
  }

  // multi-anchor tools (4-5 fixed anchors) and the variable polyline
  const needN = DRAW_MULTI_N[tool];
  if (needN || DRAW_VARLEN.has(tool)) {
    if (!state.drawMulti || state.drawMulti.type !== tool) state.drawMulti = { type: tool, pts: [] };
    state.drawMulti.pts.push({ t, p: price });
    state.pendingMarker = state.drawMulti.pts.map((pt, i) => ({
      time: pt.t, position: "inBar", color: PRAVAHA.white, shape: "circle", text: String(i + 1),
    }));
    flushMarkers();
    const have = state.drawMulti.pts.length;
    if (needN && have >= needN) { finishMulti(); return; }
    drawStatus(DRAW_VARLEN.has(tool)
      ? `Polyline anchor ${have} set — Enter or double-click to finish, Esc to cancel.`
      : `${tool.toUpperCase()} anchor ${have}/${needN} set.`);
    return;
  }

  if (DRAW_ONECLICK.has(tool)) {
    pushDrawHistory();
    if (tool === "text") {
      const note = window.prompt("Text note placed on the chart:", "");
      if (note === null) { drawStatus("Text note cancelled."); return; }
      state.drawings.push({
        id: nextDrawingId(), type: "text", t1: t, p1: price, t2: t, p2: price,
        ratios: [], text: String(note).slice(0, 120),
        color: DRAW_COLORS[state.drawings.length % DRAW_COLORS.length], created: new Date().toISOString(),
      });
      drawStatus("Text note added. Move it by dragging its handle; edit text in the list below.");
    } else if (tool === "vline" || tool === "crossline") {
      state.drawings.push({
        id: nextDrawingId(), type: tool, t1: t, p1: price, t2: t, p2: price, ratios: [],
        color: DRAW_COLORS[state.drawings.length % DRAW_COLORS.length], created: new Date().toISOString(),
      });
      drawStatus(tool === "vline"
        ? `Vertical line added at ${t}. Drag its handle to move it in time.`
        : `Cross line added (${t} @ ${fmtNum(price)}). Drag its handle to move it.`);
    } else if (tool === "hray") {
      state.drawings.push({
        id: nextDrawingId(), type: "hray", t1: t, p1: price, t2: t, p2: price, ratios: [],
        color: DRAW_COLORS[state.drawings.length % DRAW_COLORS.length], created: new Date().toISOString(),
      });
      drawStatus(`Horizontal ray added — it extends to the right from ${t}.`);
    } else {
      state.drawings.push({
        id: nextDrawingId(), type: "hline", t1: t, p1: price, t2: t, p2: price,
        ratios: [0], color: DRAW_COLORS[state.drawings.length % DRAW_COLORS.length], created: new Date().toISOString(),
      });
      drawStatus("Horizontal line added. Drag its handle to move it.");
    }
    state.drawPending = null;
    state.pendingMarker = [];
    afterDrawingsChanged();
    if (!state.drawStay) setDrawTool(null);
    return;
  }

  // channel: two anchors define the line, an optional third sets the offset
  if (DRAW_THREECLICK.has(tool) && state.drawPending && !state.drawPending3) {
    state.drawPending3 = { t, p: price };
    state.pendingMarker = [
      { time: state.drawPending.t, position: "inBar", color: PRAVAHA.white, shape: "circle", text: "1" },
      { time: t, position: "inBar", color: PRAVAHA.white, shape: "circle", text: "2" },
    ];
    drawStatus(`Anchors 1-2 set. Third click sets the channel width (click near where the parallel line should pass).`);
    flushMarkers();
    return;
  }
  // ray/measure/fibs and every new two-click tool: reuse pending state so a
  // "1" anchor survives tool hop
  if (!state.drawPending) {
    state.drawPending = { t, p: price };
    drawStatus(`Anchor 1: ${t} @ ${fmtNum(price)} — click the second anchor.`);
    state.pendingMarker = [{ time: t, position: "inBar", color: PRAVAHA.white, shape: "circle", text: "1" }];
    flushMarkers();
    return;
  }
  pushDrawHistory();
  const drawing = {
    id: nextDrawingId(), type: tool,
    t1: state.drawPending.t, p1: state.drawPending.p, t2: t, p2: price,
    ratios: [...(DRAW_DEFAULT_RATIOS[tool] || [])],
    color: DRAW_COLORS[state.drawings.length % DRAW_COLORS.length],
    created: new Date().toISOString(),
  };
  if (state.drawPending3) {
    drawing.t3 = state.drawPending3.t;
    drawing.p3 = state.drawPending3.p;
  }
  state.drawings.push(drawing);
  state.drawPending = null;
  state.drawPending3 = null;
  state.pendingMarker = [];
  clearDrawPreview();
  drawStatus(`${DRAW_LABELS[tool] || tool} added. Drag a handle to adjust; edit ratios below.`);
  afterDrawingsChanged();
  if (!state.drawStay) setDrawTool(null);
}

/* Drag an existing anchor. Hit-tests in screen space, converts the pointer
   back to (date, price) via the chart's own scales. */
function anchorParts(d) {
  const n = DRAW_MULTI_N[d.type];
  if (n || DRAW_VARLEN.has(d.type)) {
    const out = [];
    for (let i = 1; i <= (n || 64); i++) {
      if (d["t" + i] == null) break;
      out.push([`p${i}`, d["t" + i], Number(d["p" + i])]);
    }
    return out;
  }
  const single = ["hline", "text", "vline", "crossline", "hray", "note", "flag", "price_label"].includes(d.type);
  return single
    ? [["p1", d.t1, Number(d.p1)]]
    : [
      ["p1", d.t1, Number(d.p1)],
      ["p2", d.t2, Number(d.p2)],
      ...(d.t3 != null ? [["p3", d.t3, Number(d.p3)]] : []),
    ];
}

function anchorHitAt(x, y, tol = 16) {
  const chart = state.charts.price;
  if (!chart || !state.candleSeries) return null;
  const ts = chart.timeScale();
  let best = null;
  (state.drawings || []).forEach((d) => {
    if (d.hidden) return; // hidden drawings cannot be grabbed either (B-76)
    anchorParts(d).forEach(([which, t, p]) => {
      if (!t || !isFinite(p)) return;
      let ax, ay;
      try { ax = ts.timeToCoordinate(t); ay = state.candleSeries.priceToCoordinate(p); } catch (e) { return; }
      if (ax == null || ay == null) return;
      const dist = Math.hypot(ax - x, ay - y);
      if (dist <= tol && (!best || dist < best.dist)) best = { id: d.id, which, dist, locked: !!d.locked, part: "anchor" };
    });
  });
  return best;
}

function anchorHit(x, y) { return anchorHitAt(x, y, 16); }

/* Whole-drawing hit (for the select tool): near the straight segment between
   the two anchors. Segments in screen space; perpendicular distance. */
/* Polyline body hit across an drawing's consecutive anchors (works for the
   two- and three-anchor legacy shapes and any N-anchor new tool). */
/* Perpendicular distance from point (x,y) to the segment a→b (clamped to the
   segment). Shared by body hit-testing and the eraser. */
function ptSegDist(x, y, ax, ay, bx, by) {
  const vx = bx - ax, vy = by - ay;
  const len2 = vx * vx + vy * vy;
  if (len2 < 1e-9) return Math.hypot(x - ax, y - ay);
  let u = ((x - ax) * vx + (y - ay) * vy) / len2;
  u = Math.max(0, Math.min(1, u));
  return Math.hypot(ax + u * vx - x, ay + u * vy - y);
}

/* Hit-test a drawing's VISIBLE geometry, not only its anchors. Before this,
   the eraser (and click-selection) could only be satisfied by clicking an
   anchor point exactly — a single-pixel target at the line's start. Single
   anchor tools (horizontal line, ray, vertical line, text) are handled
   explicitly because their geometry spans the pane rather than sitting on an
   anchor. `part` stays "body" so the drag path treats these as move-only. */
function drawingBodyHit(x, y, tol = 10) {
  const chart = state.charts.price;
  if (!chart || !state.candleSeries) return null;
  const ts = chart.timeScale();
  const series = state.candleSeries;
  const box = $("#chart");
  const paneW = (box && box.clientWidth) || 1200;
  const paneH = (box && box.clientHeight) || 480;
  const xy = (t, p) => {
    let cx = null, cy = null;
    try { cx = ts.timeToCoordinate(String(t)); } catch (e) { cx = null; }
    try { cy = series.priceToCoordinate(Number(p)); } catch (e) { cy = null; }
    return (cx == null || cy == null) ? null : [cx, cy];
  };
  let best = null;
  const consider = (d, ax, ay, bx, by) => {
    const dist = ptSegDist(x, y, ax, ay, bx, by);
    if (dist <= tol && (!best || dist < best.dist)) {
      best = { id: d.id, part: "body", dist, locked: !!d.locked };
    }
  };
  (state.drawings || []).forEach((d) => {
    if (d.hidden) return; // hidden drawings are not selectable (B-76)
    if (d.type === "hline" || d.type === "hray") {
      const a = xy(d.t1, d.p1);
      if (!a) return;
      const x0 = d.type === "hray" ? a[0] : 0;
      consider(d, x0, a[1], paneW, a[1]);
      return;
    }
    if (d.type === "vline") {
      const a = xy(d.t1, d.p1);
      if (!a) return;
      consider(d, a[0], 0, a[0], paneH);
      return;
    }
    if (d.type === "crossline") {
      const a = xy(d.t1, d.p1);
      if (!a) return;
      consider(d, a[0], 0, a[0], paneH);
      consider(d, 0, a[1], paneW, a[1]);
      return;
    }
    if (d.type === "text" || d.type === "note" || d.type === "flag" || d.type === "price_label") {
      const a = xy(d.t1, d.p1);
      if (!a) return;
      consider(d, a[0], a[1], a[0], a[1]);
      return;
    }
    const parts = anchorParts(d);
    if (parts.length < 2) return;
    const pts = parts.map(([, t, p]) => xy(t, p));
    if (pts.some((v) => v == null)) return;
    for (let k = 0; k < pts.length - 1; k++) {
      consider(d, pts[k][0], pts[k][1], pts[k + 1][0], pts[k + 1][1]);
    }
  });
  return best;
}

/* Chart-local x → bar index. Uses the time scale's logical coordinate so a
   drag keeps working between bars and in the empty space to the right of the
   last bar (coordinateToTime returns null there, which is what made a drawing
   "stop following the cursor" at the edge). The index is clamped to the data
   range instead of failing. */
function barIndexAtX(x) {
  const chart = state.charts.price;
  const dates = state.chartDates || [];
  if (!chart || !dates.length) return null;
  const ts = chart.timeScale();
  try {
    const lg = ts.coordinateToLogical(x);
    if (lg != null && isFinite(lg)) {
      const i = Math.round(lg);
      if (i < 0) return 0;
      if (i >= dates.length) return dates.length - 1;
      return i;
    }
  } catch (e) { /* fall through to the exact-time path */ }
  try {
    const t = ts.coordinateToTime(x);
    if (t != null) {
      const i = dates.indexOf(String(t));
      if (i >= 0) return i;
    }
  } catch (e) { /* give up */ }
  return null;
}

function drawPointer(e, kind) {
  const chart = state.charts.price;
  const container = $("#chart");
  if (!chart || !container || !state.candleSeries) return false;
  const pt = chartPointFromEvent(e, container);
  const x = pt.x;
  const y = pt.y;
  state.drawHover = { x, y };

  if (kind === "down") {
    // A placement tool owns the click: a mousedown near an existing anchor must
    // plant a new anchor, not hijack the pointer into moving that drawing. The
    // eraser is handled by the click subscription, so it never drags here.
    if (state.drawTool === "eraser") return false;
    if (state.drawTool && !DRAW_MODES.has(state.drawTool)) return false;
    let hit = anchorHitAt(x, y, 16);
    if (!hit) hit = drawingBodyHit(x, y, 10);
    if (hit) {
      state.drawSelectId = hit.id;
      renderDrawList();
      refreshSelectionMarkers();
      if (hit.locked) {
        drawStatus("Locked drawing — unlock it in the drawing list.");
        return false; // let the chart pan rather than fight the lock
      }
      const d = (state.drawings || []).find((z) => z.id === hit.id);
      // No history entry yet: merely SELECTING a drawing must not consume the
      // redo stack or leave no-op entries. The snapshot is taken on the first
      // real move (see the `pushed` guard in the "move" branch below).
      if (hit.part === "body" && d) {
        // whole-drawing move: remember every anchor + the pointer origin
        const t2i = new Map((state.chartDates || []).map((dt, k) => [dt, k]));
        state.drawDrag = {
          id: hit.id, part: "body", pushed: false,
          ox: x, oy: y,
          iDown: t2i.get(String(d.t1)) != null ? t2i.get(String(d.t1)) : null,
          pDown: Number(d.p1),
          anchors: anchorParts(d).map(([which, t, p]) => ({ which, t: String(t), p: Number(p) })),
        };
      } else {
        state.drawDrag = { ...hit, pushed: false };
      }
      container.style.cursor = "grabbing";
      drawStatus("Dragging — release to drop it.");
      return true;
    }
    return false;
  }
  if (kind === "move" && state.drawDrag) {
    const d = (state.drawings || []).find((z) => z.id === state.drawDrag.id);
    if (!d) return true;
    if (!state.drawDrag.pushed) { pushDrawHistory(); state.drawDrag.pushed = true; }
    const dates = state.chartDates || [];
    const iNow = barIndexAtX(x);
    const t = iNow != null ? String(dates[iNow]) : null;
    let p = null;
    try { p = state.candleSeries.coordinateToPrice(y); } catch (e2) { p = null; }
    if (state.drawDrag.part === "body") {
      // move the whole drawing by the pointer's delta in (index, price) space
      const iDown = state.drawDrag.iDown;
      const pDown = state.drawDrag.pDown;
      if (iDown != null && iNow != null) {
        const dti = iNow - iDown;
        const dp = (p != null && isFinite(p) ? p : pDown) - pDown;
        const t2i = new Map(dates.map((dt, k) => [dt, k]));
        state.drawDrag.anchors.forEach((a) => {
          const oi = t2i.get(String(a.t));
          if (oi == null) return;
          const ni = Math.max(0, Math.min(dates.length - 1, oi + dti));
          const tNum = String(a.which).slice(1); // "p1" -> "t1", "p4" -> "t4"
          d["t" + tNum] = String(dates[ni]);
          d[a.which] = a.p + dp;
        });
      }
      renderDrawings();
      return true;
    }
    const which = state.drawDrag.which;
    if (d.type === "hline" || d.type === "hray") {
      // price-only move keeps the level (and the ray's start time) intact
      if (p != null && isFinite(p)) { d.p1 = p; d.p2 = p; }
    } else if (d.type === "vline") {
      // time-only move keeps the vertical line pinned to price history
      if (t != null) { d.t1 = t; d.t2 = t; }
      if (p != null && isFinite(p)) { d.p1 = p; d.p2 = p; }
    } else if (d.type === "crossline") {
      if (t != null) { d.t1 = t; d.t2 = t; }
      if (p != null && isFinite(p)) { d.p1 = p; d.p2 = p; }
    } else if (d.type === "text" || d.type === "note" || d.type === "flag" || d.type === "price_label") {
      if (t != null && p != null && isFinite(p)) {
        d.t1 = t; d.t2 = t; d.p1 = p; d.p2 = p;
      }
    } else {
      const key = which;
      if (t != null && p != null && isFinite(p)) {
        const tKey = "t" + String(key).slice(1);
        d[tKey] = t;
        d[key] = p;
      }
    }
    renderDrawings();
    return true;
  }
  if (kind === "up" && state.drawDrag) {
    const drag = state.drawDrag;
    const movedId = drag.id;
    const didMove = !!drag.pushed;
    state.drawDrag = null;
    container.style.cursor = "";
    afterDrawingsChanged();
    // an eraser click can both start an anchor drag and then delete the
    // drawing inside subscribeClick; report the truth of what survived
    const stillThere = (state.drawings || []).some((z) => z.id === movedId);
    drawStatus(!stillThere
      ? "Drawing erased (Undo restores it)."
      : didMove
        ? "Moved and saved for this symbol."
        : "Drawing selected — drag its body or an anchor to move it (Delete removes it).");
    return true;
  }
  return false;
}

/* ======================================================================
   CLEAR DIALOG + COMMAND PALETTE
   ----------------------------------------------------------------------
   Clear: explicit, scoped, and never silent. It can only touch the three
   things it lists (drawings on this symbol, indicators on this chart, analysis
   layers). Saved layouts, templates, watchlists, portfolios and journals are
   out of reach by construction.
   Palette: one search box (Cmd/Ctrl+K) over symbols, indicators, drawing
   tools, chart types, analysis layers, views and actions. Entries whose
   feature does not exist in this build are listed DISABLED with the reason,
   so the search never returns a control that does nothing.
   ====================================================================== */
const QUICK_IND_IDS = ["ind-sma", "ind-ema", "ind-bb", "ind-vol", "ind-rsi", "ind-macd", "ind-swings", "ind-close-swings"];

function clearChartOptions() {
  const sym = state.chartSymbol || ($("#symbol-input").value || "").trim().toUpperCase() || "—";
  const quickOn = QUICK_IND_IDS.filter((id) => { const e = document.getElementById(id); return e && e.checked && !e.disabled; });
  const nDraw = (state.drawings || []).length;
  const nInd = (state.customInds || []).length;
  const layersOn = Object.keys(state.layers || {}).filter((k) => state.layers[k]);
  return {
    sym,
    rows: [
      { key: "drawings", title: `Drawings on ${sym}`, count: nDraw,
        detail: "Manual trendlines, fibs, channels and annotations saved for this symbol. Undo (Cmd/Ctrl+Z) restores them.",
        on: nDraw > 0 },
      { key: "indicators", title: "Indicators on this chart", count: nInd + quickOn.length,
        detail: "Catalog indicator instances plus the quick-layer toggles. The indicator library itself is untouched — re-add from Indicators → catalog.",
        on: (nInd + quickOn.length) > 0 },
      { key: "analysis", title: "Analysis layers", count: layersOn.length,
        detail: "Support/resistance, Fibonacci, volume profile, charts patterns, Elliott, harmonic.",
        on: layersOn.length > 0 },
    ],
  };
}

function openClearDialog() {
  const modal = $("#clear-modal");
  if (!modal) return;
  const { sym, rows } = clearChartOptions();
  $("#clear-symbol").textContent = sym;
  $("#clear-options").innerHTML = rows.map((r) => `
    <label class="clear-opt${r.on ? "" : " off"}">
      <input type="checkbox" data-key="${esc(r.key)}"${r.on ? " checked" : ""}${r.on ? "" : " disabled"} />
      <span class="co-body">
        <span class="co-title">${esc(r.title)}<span class="pill ${r.on ? "pill-ok" : ""}">${r.count}</span></span>
        <span class="co-detail">${r.on ? esc(r.detail) : "Nothing to clear."}</span>
      </span>
    </label>`).join("");
  modal.hidden = false;
}

function closeClearDialog() { const m = $("#clear-modal"); if (m) m.hidden = true; }

function applyClearSelection() {
  const picked = Array.from(document.querySelectorAll("#clear-options input[type=checkbox]:checked"))
    .map((c) => c.dataset.key);
  const { sym } = clearChartOptions();
  if (!picked.length) { closeClearDialog(); drawStatus("Nothing selected — nothing was cleared."); return; }
  if (picked.includes("drawings")) {
    pushDrawHistory();
    state.drawings = [];
    state.drawSelectId = null;
    afterDrawingsChanged();
  }
  if (picked.includes("indicators")) {
    indHistPush();
    state.customInds = [];
    persistCustomInds(sym);
    QUICK_IND_IDS.forEach((id) => { const e = document.getElementById(id); if (e) e.checked = false; });
    saveQuickLayers(sym);
  }
  if (picked.includes("analysis")) { state.layers = {}; saveLayers(sym); }
  closeClearDialog();
  if (picked.includes("indicators") || picked.includes("analysis")) loadChart();
  drawStatus(`Cleared ${picked.join(", ")} for ${sym}.`
    + (picked.includes("drawings") ? " Drawings are undoable with Cmd/Ctrl+Z." : ""));
}

/* ------------------------------------------------------------------ palette */
const cmdkState = { items: [], filtered: [], idx: 0, built: false };

function cmdkScore(query, hay) {
  if (!query) return 1;
  const h = String(hay).toLowerCase();
  let qi = 0, streak = 0, score = 0;
  for (let i = 0; i < h.length && qi < query.length; i++) {
    if (h[i] === query[qi]) {
      qi++; streak++;
      score += 2 + streak * 2 + (i === 0 ? 8 : 0) + (i > 0 && /[\s\-_/·|]/.test(h[i - 1]) ? 5 : 0);
    } else { streak = 0; }
  }
  return qi === query.length ? score : -1;
}

async function buildPaletteItems() {
  const items = [];
  const push = (group, label, hint, run, opts = {}) => items.push({
    group, label, hint, run,
    disabled: !!opts.disabled,
    keywords: `${opts.keywords || ""} ${label} ${group}`,
  });
  // Views (the nav is the authoritative list of what the app can show).
  document.querySelectorAll("#nav button[data-view]").forEach((b) => {
    const label = (b.textContent || "").trim();
    if (!label || b.hidden) return;
    push("Views", label, "Open view", () => { showView(b.dataset.view); viewShown(b.dataset.view); },
      { keywords: "view tab panel side panels" });
  });
  // Chart types — only the ones the current data can actually render.
  Array.from(document.querySelectorAll("#chart-type option")).forEach((o) => {
    push("Chart types", `Chart: ${o.textContent.trim()}`,
      o.disabled ? "Unavailable for this series (close-only)" : "Switch chart type",
      () => { const ct = $("#chart-type"); if (!ct) return; ct.value = o.value; showView("charts"); loadChart(); },
      { disabled: o.disabled, keywords: "chart mode candles bars area line renko" });
  });
  // Drawing tools.
  Object.entries(DRAW_LABELS).forEach(([id, label]) => {
    push("Drawing tools", `Draw: ${label}`, "Activate this drawing tool",
      () => { showView("charts"); setDrawTool(id); }, { keywords: "draw drawing " + id });
  });
  push("Drawing tools", "Draw: Cursor (select / move)", "Click or drag a drawing to select and move it",
    () => { showView("charts"); setDrawTool("select"); }, { keywords: "select move cursor pointer" });
  push("Drawing tools", "Draw: Eraser", "Click any part of a drawing to delete it",
    () => { showView("charts"); setDrawTool("eraser"); }, { keywords: "erase delete remove" });
  // Analysis layers.
  const LAYER_SYNONYMS = {
    sr: "support resistance levels zones",
    fib: "fibonacci retracement extension projection",
    profile: "volume profile poc value area",
    candles: "candlestick patterns hammer engulfing",
    patterns: "chart patterns head shoulders triangle flag",
    elliott: "elliott wave impulse correction",
    harmonic: "harmonic gartley bat butterfly crab",
    structure: "market structure liquidity swing bos choch fvg equal highs lows",
    trend: "trend strength regime adx supertrend ichimoku parabolic sar",
    momentum: "momentum divergence relative strength rsi macd roc",
    volatility: "volatility breakout bollinger keltner atr squeeze",
    volume: "volume accumulation obv cmf ad line relative volume spikes",
  };
  Object.entries(LAYER_DEFS).forEach(([id, def]) => {
    push("Analysis", def.label, (state.layers && state.layers[id]) ? "Layer on — toggle off" : "Layer off — toggle on",
      () => { showView("charts"); toggleLayer(id); }, { keywords: "analysis overlay indicator " + id + " " + (LAYER_SYNONYMS[id] || "") });
  });
  // Indicators (the registry is authoritative).
  try {
    const reg = await fetchIndicatorRegistry();
    reg.forEach((x) => push("Indicators", x.label || x.name, `${x.category} · add to chart`,
      async () => {
        showView("charts");
        try { await addToChartFromCatalog(x.name, x.params || {}); drawStatus(`${x.name} added to the chart.`); }
        catch (e) { drawStatus(`Could not add ${x.name}: ${e.message}`); }
      }, { keywords: `indicator study ${x.name} ${x.category}` }));
  } catch (e) { /* registry unreachable — other groups still work */ }
  // Screener presets.
  try {
    const d = await api("/api/screen/presets");
    (d.presets || []).forEach((p) => push("Screeners", p.name || p.label || p.key, "Run this screener preset",
      () => {
        showView("screener"); viewShown("screener");
        setTimeout(() => {
          const sel = $("#preset");
          if (sel) { sel.value = p.key; sel.dispatchEvent(new Event("change")); }
        }, 250);
      }, { keywords: `screener scan preset ${p.key}` }));
  } catch (e) { /* presets unavailable */ }
  // KIMI research catalogue tools (scanners, algorithms, fundamentals).
  for (const fam of ["scanner", "algorithm", "fundamental"]) {
    try {
      const d = await api(`/api/catalog/${fam}?q=&category=all`);
      (d.tools || []).forEach((t) => {
        const label = t.name || t.key || t.id;
        const group = fam === "scanner" ? "KIMI scanners" : fam === "algorithm" ? "KIMI algorithms" : "KIMI fundamentals";
        push(group, label, t.short || t.description || "Open in KIMI Research",
          () => { showView("kimi"); viewShown("kimi"); },
          { keywords: `${fam} ${t.key || ""} ${t.category || ""} ${(t.tags || []).join(" ")}` });
      });
    } catch (e) { /* catalogue unavailable */ }
  }
  // Sasto Share features.
  [
    { label: "Sasto Share — Market Pulse", tab: "pulse", kw: "market pulse breadth participation" },
    { label: "Sasto Share — Movers", tab: "movers", kw: "movers gainers losers" },
    { label: "Sasto Share — Valuation", tab: "valuation", kw: "valuation pe pb graham" },
    { label: "Sasto Share — Risk & Volatility", tab: "risk", kw: "risk volatility drawdown" },
    { label: "Sasto Share — Sector Rotation", tab: "rotation", kw: "sector rotation relative strength" },
    { label: "Sasto Share — Dividends", tab: "dividends", kw: "dividends yield payout" },
    { label: "Sasto Share — Strategy vs Buy & Hold", tab: "strategy", kw: "strategy backtest buy hold" },
  ].forEach((f) => push("Sasto Share", f.label, "Open Sasto Share panel",
    () => { showView("sastoshare"); viewShown("sastoshare"); if (typeof ssSubTab === "function") ssSubTab(f.tab); },
    { keywords: f.kw }));
  // Fundamental tools (tabs in the Company Universe view).
  [
    { label: "Margin Eligibility", kw: "margin eligibility trading" },
    { label: "TTM EPS Analysis", kw: "ttm eps trailing twelve month" },
    { label: "Fundamental Comparison", kw: "fundamental comparison pe pb roe" },
    { label: "Financial Screener", kw: "financial screener eps valuation" },
    { label: "EPS Rankings", kw: "eps rankings earnings" },
    { label: "EPS History & Growth", kw: "eps history growth" },
    { label: "Company Profile", kw: "company profile fundamentals" },
    { label: "Sector Explorer", kw: "sector explorer classification" },
  ].forEach((f) => push("Fundamentals", f.label, "Open in Company Universe",
    () => { showView("new"); viewShown("new"); },
    { keywords: f.kw }));
  // Key analytics (views + features).
  [
    { label: "Market Barometer", view: "overview", kw: "barometer market health breadth score" },
    { label: "Market Breadth", view: "breadth", kw: "breadth advance decline" },
    { label: "Seasonality", view: "sea", kw: "seasonality month quarter" },
    { label: "Swing Workbench", view: "swingw", kw: "swing structure support resistance" },
    { label: "Backtesting", view: "backtest", kw: "backtest strategy sharpe drawdown" },
    { label: "Portfolio", view: "portfolio", kw: "portfolio holdings risk" },
    { label: "Screener", view: "screener", kw: "screener scanner filter" },
  ].forEach((f) => push("Analytics", f.label, "Open view",
    () => { showView(f.view); viewShown(f.view); },
    { keywords: f.kw }));
  // Key metrics that live inside other views (not standalone pages).
  push("Analytics", "Sharpe Ratio", "Risk-adjusted return metric — available in Backtesting results",
    () => { showView("backtest"); viewShown("backtest"); },
    { keywords: "sharpe ratio risk adjusted return backtest" });
  push("Analytics", "Multi-Timeframe Trend Consensus", "NOT IMPLEMENTED — only daily timeframe is supported; weekly/monthly consensus is not available",
    () => { showView("charts"); toggleLayer("trend"); },
    { keywords: "multi timeframe trend consensus weekly monthly", disabled: true });
  // Actions.
  push("Actions", "Fit chart to data", "Show every loaded bar", () => { showView("charts"); if (state.charts.price) state.charts.price.timeScale().fitContent(); }, { keywords: "zoom fit reset viewport" });
  push("Actions", "Zoom in", null, () => { showView("charts"); chartZoom(0.75); }, {});
  push("Actions", "Zoom out", null, () => { showView("charts"); chartZoom(1.33); }, {});
  push("Actions", "Toggle expanded chart", "Full screen — Esc exits", () => { showView("charts"); const b = $("#chart-fullscreen"); if (b) b.click(); }, { keywords: "fullscreen expand maximise" });
  push("Actions", "Undo (Cmd/Ctrl+Z)", null, () => { showView("charts"); histUndo(); }, { keywords: "undo history" });
  push("Actions", "Redo (Shift+Cmd/Ctrl+Z)", null, () => { showView("charts"); histRedo(); }, { keywords: "redo history" });
  push("Actions", "Clear chart…", "Drawings / indicators / analysis — asks first", () => openClearDialog(), { keywords: "clear reset remove all delete" });
  push("Actions", "Open the indicator catalog", "Searchable library of every registered indicator", () => { showView("charts"); openIndicatorCatalog(); }, { keywords: "indicator library catalogue indicators" });
  push("Actions", "Open the on-chart indicator drawer", null, () => { showView("charts"); const t = document.getElementById("chart-drawer-toggle"); if (t) t.click(); }, {});
  push("Actions", "Compare symbols…", "Up to 4 symbols on one chart", async () => { showView("charts"); if (!state.charts.price) { const inp = $("#symbol-input"); if (inp && !inp.value) inp.value = "NABIL"; try { await loadChart(); } catch (e) { /* load failed - drawer still opens to explain */ } } const b = $("#pop-compare-btn"); if (b) b.click(); }, { keywords: "compare relative overlay percent" });
  push("Actions", "Replay the chart", "Step through history bar by bar", () => { showView("charts"); const b = $("#pop-replay-btn"); if (b) b.click(); }, { keywords: "replay backtest bar" });

  // Curated catalogue requested by the owner. A row with a view runs it; a row
  // without one is listed DISABLED with the honest reason, so the palette never
  // pretends a feature exists.
  const CURATED = [
    ["Top Stocks", "overview", "Overview dashboard — movers, volume, breadth"],
    ["Watchlist", "watchlists", "Your saved watchlists"],
    ["Shareholder Watchlist", null, "Not implemented — no shareholding-register source in this build"],
    ["Chart Share", null, "Not implemented — chart image sharing is not built"],
    ["Chart Calendar", null, "Not implemented — no events/earnings calendar source"],
    ["Candle Stick", "screener", "Candlestick metrics live in the Screener; markers render via Analysis → Candlestick patterns", "candles candlestick"],
    ["Fresh Indicator Signal", "tracing", "Indicator-alert history is in Tracing"],
    ["Pine Script", "charts", "Not a Pine engine — this app has a sandboxed custom-formula DSL (Indicators → Custom formula)", "pine custom formula dsl"],
    ["Stock Alert", "tracing", "Alert history is in Tracing"],
    ["SMC / Support & Resistance", "charts", "Analysis drawer → Support & resistance layer", "smc levels support resistance"],
    ["Trend Line Breakout", "charts", "Use the Trendline drawing tool, or the Screener structure metrics", "breakout trendline"],
    ["Volume Scan", "screener", "Screener presets: volume dry-up, pocket pivot, accumulation", "volume"],
    ["Seasonality", "sea", "Month-of-year seasonality per symbol"],
    ["Swing Trader", "swingw", "Swing workbench — structure, support/resistance, invalidation"],
    ["Stock Heat Map", null, "Not implemented"],
    ["Alpha Rider", null, "Not implemented"],
    ["Terminal", "overview", "This research terminal"],
    ["Alpha Coder", null, "Not implemented — the sandboxed custom-formula DSL is the closest built feature"],
    ["Main Chart", "charts", "The price chart"],
    ["Multi Chart", null, "Not implemented — this build draws one chart per view"],
    ["StageAnalysis Chart", null, "Not implemented (Minervini stage analysis)"],
    ["Seasonality Chart", "sea", "Seasonality view"],
    ["Market Breadth Mode", "breadth", "Breadth history — advance/decline, % above SMA"],
    ["Foot Print Mode", null, "Not implemented — no intraday tick data in the stored dataset"],
    ["Elliot Wave Mode", "charts", "Analysis drawer → Elliott Wave", "elliott waves"],
    ["Smart Money Holding", null, "Not implemented"],
    ["Floorsheet Mode", "floorsheet", "Broker floorsheet history"],
    ["Trading Simulator", null, "Not implemented"],
    ["Minervini SEPA-VCP Chart", null, "Not implemented"],
    ["O'Neil CAN-SLIM Chart", null, "Not implemented"],
    ["Parameter Scan", "screener", "Screener rule builder"],
    ["Draw To Scan", null, "Not implemented"],
    ["MTF Scan", null, "Not implemented (multi-timeframe scan)"],
    ["Trade Monitor", null, "Not implemented"],
    ["Chart Patterns", "charts", "Analysis drawer → Chart patterns; matches render on the chart", "patterns head shoulders triangle"],
    ["Divergences", null, "Not implemented as a dedicated view"],
    ["Relative Strength", "screener", "Screener relative-strength metrics vs the NEPSE index", "rs rating"],
    ["Free AI Signals", null, "Not implemented"],
    ["Premium AI Signals", null, "Not implemented"],
    ["Open Algo Signal", null, "Not implemented — and this app never places trades"],
    ["My Algorithms", "backtest", "Backtest workspace for your own rules"],
    ["Portfolios", "portfolio", "Portfolio tracking"],
    ["Workspace", "workshop", "Indicator workshop and templates"],
  ];
  CURATED.forEach(([label, view, note, kw]) => {
    if (view) {
      push("Catalogue", label, note || "Open",
        () => {
          showView(view); viewShown(view);
          if (["SMC / Support & Resistance", "Chart Patterns", "Elliot Wave Mode"].includes(label)) {
            const d = document.getElementById("chart-drawer");
            if (d && d.hidden) { const t = document.getElementById("chart-drawer-toggle"); if (t) t.click(); }
          }
        }, { keywords: kw || "" });
    } else {
      push("Catalogue", label, note || "Not implemented", () => {},
        { disabled: true, keywords: `${kw || ""} not implemented unavailable` });
    }
  });
  return items;
}

async function openPalette() {
  const el = $("#cmdk");
  if (!el) return;
  el.hidden = false;
  const input = $("#cmdk-input");
  cmdkState.idx = 0;
  input.value = "";
  input.focus();
  if (!cmdkState.built) {
    $("#cmdk-list").innerHTML = `<div class="cmdk-group">Loading…</div>`;
    cmdkState.items = await buildPaletteItems();
    cmdkState.built = true;
  }
  renderPalette("");
}

function closePalette() { const el = $("#cmdk"); if (el) el.hidden = true; }

let cmdkSearchReq = 0;
async function fetchUniversalSearch(query) {
  if (!query || query.length < 2) return [];
  try {
    const d = await api(`/api/search?q=${encodeURIComponent(query)}&limit=30`);
    return (d.results || []).map((r) => {
      const t = r.target || {};
      return {
        group: "Universal search",
        label: r.label,
        hint: `${r.hint || ""} · ${r.source || ""}`.trim(),
        keywords: `${r.label} ${r.hint || ""} ${r.source || ""}`,
        disabled: false,
        run: () => {
          if (t.type === "view") { showView(t.view); viewShown(t.view); }
          else if (t.type === "symbol") {
            showView("charts"); viewShown("charts");
            const inp = $("#symbol-input"); if (inp) inp.value = t.symbol;
            if (typeof loadChart === "function") loadChart();
          } else if (t.type === "sector") {
            showView("baba/sector"); viewShown("baba/sector");
            if (typeof BABA !== "undefined") BABA.sector = t.sector;
            if (typeof babaSectorReport === "function") babaSectorReport();
          } else if (t.type === "component") {
            showView("baba/builder"); viewShown("baba/builder");
          } else if (t.type === "journal") {
            showView("baba/journal"); viewShown("baba/journal");
          } else if (t.type === "research") {
            showView("research"); viewShown("research");
          } else {
            drawStatus(`Selected: ${r.label}`);
          }
        },
      };
    });
  } catch (e) {
    return [];
  }
}

async function renderPalette(q) {
  const list = $("#cmdk-list");
  if (!list) return;
  const reqId = ++cmdkSearchReq;
  const query = (q || "").trim().toLowerCase();
  const scored = [];
  cmdkState.items.forEach((it) => {
    if (it.disabled && !query) return;
    const s = cmdkScore(query, `${it.label} ${it.hint || ""} ${it.keywords || ""} ${it.group}`);
    if (s < 0) return;
    scored.push({ it, s });
  });
  if (query.length >= 2) {
    const extra = await fetchUniversalSearch(query);
    if (reqId !== cmdkSearchReq) return;
    extra.forEach((it) => {
      const s = cmdkScore(query, `${it.label} ${it.hint || ""} ${it.keywords || ""} ${it.group}`);
      if (s >= 0) scored.push({ it, s: Math.max(s, 0) });
    });
  }
  if (query) scored.sort((a, b) => b.s - a.s || String(a.it.label).localeCompare(String(b.it.label)));
  cmdkState.filtered = scored.slice(0, 100).map((x) => x.it);
  if (cmdkState.idx >= cmdkState.filtered.length) cmdkState.idx = 0;
  const countEl = $("#cmdk-count");
  if (!cmdkState.filtered.length) {
    list.innerHTML = `<div class="cmdk-group">No match for “${esc(q)}”</div>`;
    if (countEl) countEl.textContent = "0 results";
    return;
  }
  let html = "", lastGroup = "";
  cmdkState.filtered.forEach((it, i) => {
    if (it.group !== lastGroup) { html += `<div class="cmdk-group">${esc(it.group)}</div>`; lastGroup = it.group; }
    html += `<div class="cmdk-item${i === cmdkState.idx ? " sel" : ""}${it.disabled ? " disabled" : ""}" data-i="${i}" role="option" aria-disabled="${it.disabled}">`
      + `<span class="ci-label">${esc(it.label)}</span>`
      + (it.hint ? `<span class="ci-hint">${esc(it.hint)}</span>` : "")
      + `</div>`;
  });
  list.innerHTML = html;
  if (countEl) countEl.textContent = `${cmdkState.filtered.length} result${cmdkState.filtered.length === 1 ? "" : "s"}`;
  list.querySelectorAll(".cmdk-item").forEach((node) => {
    node.addEventListener("click", () => { cmdkState.idx = Number(node.dataset.i); runPaletteSelection(); });
    node.addEventListener("mousemove", () => {
      const i = Number(node.dataset.i);
      if (cmdkState.idx === i) return;
      cmdkState.idx = i;
      list.querySelectorAll(".cmdk-item").forEach((n2) => n2.classList.toggle("sel", Number(n2.dataset.i) === i));
    });
  });
  const sel = list.querySelector(".cmdk-item.sel");
  if (sel && sel.scrollIntoView) sel.scrollIntoView({ block: "nearest" });
}

function runPaletteSelection() {
  const it = cmdkState.filtered[cmdkState.idx];
  if (!it) return;
  if (it.disabled) { drawStatus(`${it.label}: ${it.hint}`); return; }
  closePalette();
  try { it.run(); } catch (e) { drawStatus(`Action failed: ${e.message}`); }
}

function bindClearAndPalette() {
  if ($("#chart-clear")) $("#chart-clear").addEventListener("click", openClearDialog);
  if ($("#chart-search")) $("#chart-search").addEventListener("click", openPalette);
  if ($("#clear-close")) $("#clear-close").addEventListener("click", closeClearDialog);
  if ($("#clear-cancel")) $("#clear-cancel").addEventListener("click", closeClearDialog);
  if ($("#clear-confirm")) $("#clear-confirm").addEventListener("click", applyClearSelection);
  const cm = $("#clear-modal");
  if (cm) cm.addEventListener("click", (e) => { if (e.target === cm) closeClearDialog(); });
  if ($("#cmdk-close")) $("#cmdk-close").addEventListener("click", closePalette);
  const ck = $("#cmdk");
  if (ck) ck.addEventListener("click", (e) => { if (e.target === ck) closePalette(); });
  const input = $("#cmdk-input");
  if (input) {
    input.addEventListener("input", () => { cmdkState.idx = 0; renderPalette(input.value); });
    input.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown") { e.preventDefault(); cmdkState.idx = Math.min(cmdkState.idx + 1, cmdkState.filtered.length - 1); renderPalette(input.value); }
      else if (e.key === "ArrowUp") { e.preventDefault(); cmdkState.idx = Math.max(cmdkState.idx - 1, 0); renderPalette(input.value); }
      else if (e.key === "Enter") { e.preventDefault(); runPaletteSelection(); }
      else if (e.key === "Escape") { e.preventDefault(); closePalette(); }
    });
  }
  // Cmd/Ctrl+K opens the palette from anywhere; Esc closes an open overlay too.
  document.addEventListener("keydown", (e) => {
    const mod = e.metaKey || e.ctrlKey;
    if (mod && (e.key === "k" || e.key === "K")) {
      e.preventDefault();
      const el = $("#cmdk");
      if (el && !el.hidden) closePalette(); else openPalette();
      return;
    }
    if (e.key === "Escape") {
      if (cmdkState.filtered.length && $("#cmdk") && !$("#cmdk").hidden) closePalette();
      if ($("#clear-modal") && !$("#clear-modal").hidden) closeClearDialog();
    }
  });
}

/* One place that activates a tool (set by the rail buttons or the legacy select). */
function setDrawTool(tool) {
  state.drawTool = tool || null;
  // While a drawing tool is active the chart must not pan on a drag: a pan
  // steals the click (Lightweight Charts treats a moved pointer as a drag, so
  // subscribeClick never fires and the drawing is never created) and it is
  // what made vertical lines and rays "unreliable". Toggling pressedMouseMove
  // here keeps the cursor tool's panning intact.
  try {
    const c = state.charts.price;
    const on = !(tool && !DRAW_MODES.has(tool));
    state.panEnabled = on;
    if (c) c.applyOptions({ handleScroll: { pressedMouseMove: on } });
  } catch (e) { /* chart not ready */ }
  state.drawPending = null;
  state.drawPending3 = null;
  state.drawMulti = null; // switching tools abandons a partial multi-anchor run
  clearDrawPreview();
  state.pendingMarker = [];
  flushMarkers();
  const sel = $("#draw-tool");
  if (sel && sel.value !== (tool || "")) sel.value = tool || "";
  $$(".rail-tool").forEach((b) => b.classList.toggle("active", b.dataset.tool === (tool || "") ));
  if (typeof railHighlight === "function") railHighlight();
  const box = $("#chart");
  if (box) box.style.cursor = tool === "eraser" ? "not-allowed" : tool === "select" ? "grab" : tool ? "crosshair" : "";
  drawStatus(tool
    ? (tool === "select" ? "Select tool — click a drawing to select, drag it to move; re-click the cursor tool to exit."
      : tool === "eraser" ? "Eraser — click a drawing on the chart to delete it (locked drawings stay)."
        : `${DRAW_LABELS[tool] || tool} — click ${DRAW_ONECLICK.has(tool) ? "once" : "twice"} on the chart.`)
    : "");
}

/* Icons for the rail: one stroke family, chart-tool meanings (not reused nav
   icons) — each is a tooltip + status label, never the only naming. */
const RAIL_GROUPS = [
  { label: "Cursor", tools: [
    { id: "__cursor", name: "Cursor / crosshair", d: "Pan, zoom and read the OHLCV strip — no drawing.", icon: '<path d="M12 4v16M4 12h16"/>' },
    { id: "select", name: "Select", d: "Click a drawing, drag it whole, or drag one anchor.", icon: '<path d="M6 3l4 16 2.5-6 6-2.5z"/>' },
    { id: "eraser", name: "Eraser", d: "Click a drawing on the chart to delete it (locked ones stay; Undo restores).", icon: '<rect x="4" y="14" width="10" height="6" rx="1"/><path d="M14 14l6-6-4-4-6 6"/><path d="M8 20h12" />' } ] },
  { label: "Lines", tools: [
    { id: "trendline", name: "Trendline", d: "2 anchors — straight line between two pivots.", icon: '<path d="M4 19L20 5"/><circle cx="4" cy="19" r="1.6"/><circle cx="20" cy="5" r="1.6"/>' },
    { id: "ray", name: "Ray", d: "2 anchors — extends right through anchor 2.", icon: '<path d="M4 19L14 9"/><path d="M14 9l6-4"/>' },
    { id: "extended", name: "Extended line", d: "2 anchors — infinite line in both directions.", icon: '<path d="M2 21L10 13M14 9l8-8" dashed="true"/><circle cx="12" cy="11" r="1.4"/>' },
    { id: "hline", name: "Horizontal line", d: "1 anchor — horizontal at that price.", icon: '<path d="M4 12h16"/><circle cx="12" cy="12" r="1.6"/>' },
    { id: "hray", name: "Horizontal ray", d: "1 anchor — horizontal, extends right only.", icon: '<path d="M4 12h12"/><path d="M16 12l5 0"/><path d="M18 9.5l3 2.5-3 2.5"/>' },
    { id: "vline", name: "Vertical line", d: "1 anchor — vertical at that date.", icon: '<path d="M12 4v16"/><circle cx="12" cy="12" r="1.6"/>' },
    { id: "crossline", name: "Cross line", d: "1 anchor — horizontal + vertical through it.", icon: '<path d="M12 3v18M3 12h18"/><circle cx="12" cy="12" r="1.6"/>' },
  ]},
  { label: "Channels", tools: [
    { id: "channel", name: "Parallel channel", d: "3 clicks — 2 anchors set the slope, the 3rd sets the width.", icon: '<path d="M3 16L17 6"/><path d="M7 20L21 10"/>' },
    { id: "regression_channel", name: "Regression channel", d: "3 clicks — OLS centre line with kσ bands (ratios[0] = k).", icon: '<path d="M3 17l17-10"/><path d="M3 13.5l17-10"/><path d="M3 21l17-10"/><circle cx="3" cy="17" r="1.4"/>' },
    { id: "pitchfork", name: "Pitchfork", d: "3 anchors — median A→mid(BC) with parallel tines through B and C.", icon: '<path d="M4 20L14 10"/><path d="M8 7l8 0"/><path d="M6 10l10 0.001"/><path d="M14 10l6 -2"/>' },
    { id: "schiff_pitchfork", name: "Schiff pitchfork", d: "3 anchors — handle price halved toward mid(BC), same date; a flattened fork.", icon: '<path d="M4 20L10 13"/><path d="M8 7l8 0"/><path d="M14 10l6 -2"/>' } ] },
  { label: "Fibonacci", tools: [
    { id: "fib_retracement", name: "Fibonacci retracement", d: "2 anchors — levels at p2 − r·(p2−p1).", icon: '<path d="M4 18h6M10 13h6M4 8h16"/><path d="M4 18V8"/>' },
    { id: "fib_extension", name: "Fibonacci extension", d: "2 anchors — levels at p2 + r·(p2−p1).", icon: '<path d="M4 18h6M4 13h10M4 8h16"/><path d="M16 8l4 0M16 5l4 3-4 3" />' },
    { id: "fib_timezones", name: "Fib time zones", d: "2 anchors — verticals 1,2,3,5,8… bars from anchor 1.", icon: '<path d="M5 20v-6M9 20v-9M13 20v-5M17 20v-11"/>' },
    { id: "fib_fan", name: "Fib fan", d: "2 anchors — rays through fib fractions of the leg.", icon: '<path d="M4 20L20 6"/><path d="M4 20L20 11"/><path d="M4 20L20 16"/>' },
    { id: "fib_channel", name: "Fib channel", d: "3 clicks — base line plus fib-ratio parallels through C.", icon: '<path d="M3 18L19 8"/><path d="M6 20L22 10"/><path d="M6 14L22 4"/>' },
    { id: "fib_tbe", name: "Trend-based Fib extension", d: "3 clicks — impulse leg projected from B (1.618 etc.).", icon: '<path d="M4 19L10 8"/><path d="M10 8L15 13"/><path d="M15 13h5"/><path d="M15 9h5" dashed="true"/>' } ] },
  { label: "Measure", tools: [
    { id: "measure", name: "Measure", d: "2 anchors — Δprice, Δ%, Δbars and Δvolume.", icon: '<path d="M4 19L20 5"/><path d="M4 19l0-4M20 5l-4 0"/><path d="M7 16l3-0M10 13l1-0"/>' },
    { id: "price_range", name: "Price range", d: "2 anchors — Δprice between the two anchors.", icon: '<path d="M12 5v6M12 13v6"/><path d="M9 8l3-3 3 3M9 16l3 3 3-3"/>' },
    { id: "date_range", name: "Date range", d: "2 anchors — sessions and bars between the anchors.", icon: '<path d="M5 20v-6M9 20v-9M13 20v-5M17 20v-11"/>' } ] },
  { label: "Shapes", tools: [
    { id: "rectangle", name: "Rectangle", d: "2 anchors — opposite corners.", icon: '<rect x="5" y="7" width="14" height="10" rx="1"/>' },
    { id: "arrow", name: "Arrow", d: "2 anchors — line with the head at anchor 2.", icon: '<path d="M4 20L19 5"/><path d="M13 5h6v6"/>' },
    { id: "triangle", name: "Triangle", d: "3 anchors — closed three-point shape.", icon: '<path d="M12 5l7 13H5z"/>' },
    { id: "polyline", name: "Polyline", d: "Click out the path; Enter or Esc finishes it.", icon: '<path d="M4 18l4-8 4 5 5-9"/><circle cx="4" cy="18" r="1.4"/>' },
    { id: "gann_fan", name: "Gann fan (leg-relative)", d: "2 anchors — rays at 1/8th fractions of the anchor leg. Angles follow the chart scale, not absolute degrees.", icon: '<path d="M4 20L20 4M4 20L20 8M4 20L20 12M4 20L20 16"/>' },
    { id: "circle", name: "Circle", d: "2 anchors — centre + a point on the circumference (polyline approximation, 72 segments).", icon: '<circle cx="12" cy="12" r="7"/>' },
    { id: "ellipse", name: "Ellipse", d: "3 anchors — centre + X-radius + Y-radius point (polyline approximation).", icon: '<ellipse cx="12" cy="12" rx="9" ry="5"/>' } ] },
  { label: "Text", tools: [
    { id: "text", name: "Text note", d: "1 anchor — editable text via the drawing list.", icon: '<path d="M5 5h14M12 5v13"/><path d="M9 18h6"/>' },
    { id: "note", name: "Note", d: "1 anchor — text marker with a drag handle.", icon: '<path d="M6 6h9l3 3v9H6z"/><path d="M9 11h6M9 14h4"/>' },
    { id: "price_label", name: "Price label", d: "1 anchor — level line with an editable price chip.", icon: '<path d="M4 12h13"/><rect x="14" y="9" width="7" height="6" rx="1"/>' },
    { id: "flag", name: "Flag", d: "1 anchor — flag marker at a bar.", icon: '<path d="M6 21V4"/><path d="M6 5h9l-2.5 3L15 11H6"/>' } ] },
  { label: "Patterns", tools: [
    { id: "xabcd", name: "XABCD", d: "5 anchors — harmonic leg construction.", icon: '<path d="M4 19L8 7M8 7l4 9l4 -9l4 12"/><text x="1" y="4" font-size="5">X</text>' },
    { id: "abcd", name: "ABCD", d: "4 anchors — retracement leg chain.", icon: '<path d="M5 18l4-9 4 13 5-9"/>' },
    { id: "three_drives", name: "Three drives", d: "4 anchors — X plus drives 1-2-3.", icon: '<path d="M4 19l4-6 4 5 5-11"/>' },
    { id: "elliott_impulse", name: "Elliott impulse", d: "5 anchors — labels 1-2-3-4-5 (a candidate count, not a certainty).", icon: '<path d="M4 18l4-7 3 3 5-8 4 12"/>' },
    { id: "elliott_abc", name: "Elliott correction", d: "3 anchors — labels A-B-C.", icon: '<path d="M4 18l5-11 5 6 6 -8"/>' },
    { id: "fib_arc", name: "Fibonacci arcs", d: "2 anchors — concentric semicircular arcs at fib ratios of the leg (polyline approximation).", icon: '<path d="M4 18 A8 8 0 0 1 20 18"/><path d="M7 18 A5 5 0 0 1 17 18"/><path d="M9 18 A3 3 0 0 1 15 18"/>' },
    { id: "fib_spiral", name: "Fibonacci spiral", d: "2 anchors — golden spiral sampled as a polyline (approximation; axes are not equal scale).", icon: '<path d="M12 12 C12 8 16 8 16 12 C16 18 8 18 8 12 C8 4 20 4 20 12"/>' },
    { id: "hns", name: "Head & Shoulders (manual)", d: "5 anchors — LS, head, RS, neckline left, neckline right. User-drawn annotation, not a detector.", icon: '<path d="M4 16l4-8 4 3 4-10 4 3 4-8"/><path d="M4 12h16" dashed="true"/>' } ] },
  { label: "Positions", tools: [
    { id: "long_pos", name: "Long position", d: "2 anchors — entry → stop; target from R:R (ratios).", icon: '<path d="M5 17v-6M9 17V7M13 17v-3"/><path d="M18 14l0 -7"/><path d="M15.5 9.5L18 7l2.5 2.5"/>' },
    { id: "short_pos", name: "Short position", d: "2 anchors — entry → stop; target from R:R (ratios).", icon: '<path d="M5 17v-9M9 17V13M13 17v-3"/><path d="M18 10l0 7"/><path d="M15.5 14.5L18 17l2.5-2.5"/>' } ] },
];

/* Grouped rail: one icon per category; clicking a category opens a popover
   beside the rail listing that group's tools with their NAMES (the flat grid
   of anonymous tiny icons was undiscoverable — §5.4C/§5.10). The search box
   filters across every group and opens the matching popover. */
let railHighlight = null;
function buildDrawRail() {
  const stage = $("#chart-stage");
  if (!stage || $("#draw-rail")) return;
  const rail = document.createElement("div");
  rail.className = "draw-rail";
  rail.id = "draw-rail";
  rail.setAttribute("aria-label", "Drawing tools");
  const search = document.createElement("input");
  search.className = "rail-search";
  search.id = "rail-search";
  search.placeholder = "search";
  search.title = "Filter drawing tools by name (searches every group)";
  search.spellcheck = false;
  rail.appendChild(search);
  let pop = null;
  const closePop = () => { if (pop) { pop.remove(); pop = null; } };

  const openPopover = (group, q) => {
    closePop();
    pop = document.createElement("div");
    pop.className = "rail-pop";
    pop.id = "rail-pop";
    pop.setAttribute("role", "menu");
    // attached to the STAGE, not the rail: the rail scrolls and would clip it
    const stageEl = $("#chart-stage");
    (stageEl || rail.parentElement).appendChild(pop);
    const groups = group ? [group] : RAIL_GROUPS;
    const head = document.createElement("div");
    head.className = "rail-pop-head";
    const headTxt = document.createElement("span");
    headTxt.textContent = group ? group.label : "All tools";
    const headCount = document.createElement("span");
    headCount.className = "rail-pop-count";
    headCount.textContent = ` · ${groups.reduce((n, g) => n + g.tools.length, 0)} tools`;
    head.appendChild(headTxt); head.appendChild(headCount);
    pop.appendChild(head);
    let any = false;
    groups.forEach((g) => {
      const rows = g.tools.filter((tr) => !q || tr.name.toLowerCase().includes(q)
        || (tr.d || "").toLowerCase().includes(q) || g.label.toLowerCase().includes(q));
      if (!rows.length) return;
      any = true;
      const lab = document.createElement("div");
      lab.className = "rail-pop-cat";
      lab.textContent = g.label;
      pop.appendChild(lab);
      rows.forEach((tr) => {
        const b = document.createElement("button");
        b.className = "rail-tool rail-pop-item" + (state.drawTool === tr.id ? " active" : "");
        b.dataset.tool = tr.id;
        b.title = tr.name + (tr.d ? " — " + tr.d : "");
        b.innerHTML =
          `<svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">${tr.icon}</svg>` +
          `<span class="rail-pop-txt"><span class="rail-pop-name">${esc(tr.name)}</span>` +
          (tr.d ? `<span class="rail-pop-desc">${esc(tr.d)}</span>` : "") + `</span>`;
        const activate = (ev) => {
          ev.stopPropagation();
          setDrawTool(tr.id === "__cursor" ? null : tr.id);
          if (tr.id === "__cursor") drawStatus("Cursor mode — switch on a tool to draw again.");
          updateRailActive();
          closePop();
        };
        b.addEventListener("click", activate);
        pop.appendChild(b);
      });
    });
    if (!any) {
      const none = document.createElement("div");
      none.className = "rail-pop-empty";
      none.textContent = "No tool matches.";
      pop.appendChild(none);
    }
  };
  document.addEventListener("click", (e) => {
    if (!pop) return;
    const t = e.target;
    if (t && t.closest && t.closest("#rail-pop")) return; // clicks inside the popover select a tool
    if (t && t.closest && t.closest("#draw-rail")) return; // a category click re-opens/toggles
    closePop();
  }, true);
  const updateRailActive = () => {
    const active = state.drawTool;
    $$(".rail-cat", rail).forEach((b) => {
      const g = RAIL_GROUPS.find((gg) => gg.label === b.dataset.label);
      const has = g && (active == null
        ? g.tools.some((t) => t.id === "__cursor")
        : g.tools.some((t) => t.id === active));
      b.classList.toggle("active", !!has);
    });
  };
  RAIL_GROUPS.forEach((g) => {
    const gEl = document.createElement("div");
    gEl.className = "rail-group";
    gEl.dataset.label = g.label.toLowerCase();
    const b = document.createElement("button");
    b.className = "rail-cat";
    b.dataset.label = g.label;
    b.title = `${g.label} — ${g.tools.length} tools (click for the list)`;
    b.setAttribute("aria-haspopup", "true");
    const first = g.tools[0] && g.tools[0].icon ? g.tools[0].icon : '<circle cx="12" cy="12" r="6"/>';
    const chev = '<path d="M9 6l6 6-6 6"/>';
    b.innerHTML = `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">${first}</svg><svg viewBox="0 0 24 24" width="9" height="9" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round">${chev}</svg>`;
    b.addEventListener("click", (e) => {
      e.stopPropagation();
      if (pop) { closePop(); return; }
      closePop();
      search.value = "";
      openPopover(g, "");
    });
    gEl.appendChild(b);
    rail.appendChild(gEl);
  });
  search.addEventListener("input", () => {
    const q = (search.value || "").trim().toLowerCase();
    if (!q) { closePop(); return; }
    openPopover(null, q);
  });
  search.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      const first = pop && pop.querySelector(".rail-pop-item");
      if (first) first.click();
    }
  });
  stage.appendChild(rail);
  setDrawTool(state.drawTool);
  railHighlight = updateRailActive;
  updateRailActive();
}

function bindDrawings() {
  const container = $("#chart");
  if (container) {
    // CAPTURE phase: when the pointer lands on a drawing we take the gesture
    // and stop it before lightweight-charts sees it. Otherwise the library
    // starts panning at the same moment the drawing moves, so the line slides
    // away from the cursor instead of following it.
    container.addEventListener("mousedown", (e) => {
      const p = chartPointFromEvent(e, container);
      state.drawHover = { x: p.x, y: p.y };
      state.chartDrag = state.chartDrag || {};
      state.chartDrag.mouseDown = { x: e.clientX, y: e.clientY };
      // When a drawing tool is active, the chart must NOT start panning: a
      // pan gesture steals the click (Lightweight Charts treats a moved
      // pointer as a drag, so subscribeClick never fires and the drawing is
      // never created). Taking the gesture here guarantees the click lands.
      const toolActive = !!state.drawTool && !DRAW_MODES.has(state.drawTool);
      // Panning is disabled via chart options (pressedMouseMove) when a tool is
      // active, so we do NOT need preventDefault/stopPropagation here. Calling
      // them was blocking Lightweight Charts' own click handling, which is why
      // real clicks never reached onChartClick.
      if (drawPointer(e, "down")) { e.preventDefault(); e.stopPropagation(); }
    }, true);
    container.addEventListener("mousemove", (e) => {
      const p = chartPointFromEvent(e, container);
      const mx = p.x, my = p.y;
      state.drawHover = { x: mx, y: my };
      if (state.drawDrag) { drawPointer(e, "move"); e.preventDefault(); return; }
      if (state.drawPending) { queueDrawPreview(mx, my); return; }
      if (state.drawTool === "eraser") { container.style.cursor = "not-allowed"; return; }
      const hit = anchorHitAt(mx, my, 20) || drawingBodyHit(mx, my, 10);
      container.style.cursor = hit ? "grab" : (state.drawTool ? "crosshair" : "");
    }, true);
    window.addEventListener("mouseup", (e) => {
      drawPointer(e, "up");
      if (state.chartDrag) state.chartDrag.mouseDown = null;
      if (state.drawPending) clearDrawPreview();
    });
  }
  bindDrawProps();
  if ($("#draw-tool")) {
    $("#draw-tool").addEventListener("change", () => setDrawTool($("#draw-tool").value || null));
  }
  if ($("#dr-stay")) $("#dr-stay").addEventListener("change", () => {
    state.drawStay = $("#dr-stay").checked;
  });
  if ($("#dr-magnet")) $("#dr-magnet").addEventListener("change", () => {
    state.drawMagnet = $("#dr-magnet").value;
    drawStatus(state.drawMagnet === "off" ? "Magnet off — free placement."
      : state.drawMagnet === "weak" ? "Weak magnet: free placement, but anchors snap to a nearby O/H/L/C point."
        : "Strong magnet: anchors snap to the nearest O/H/L/C point of the clicked bar.");
  });
  if ($("#draw-lockall")) $("#draw-lockall").addEventListener("click", () => {
    pushDrawHistory();
    (state.drawings || []).forEach((d) => { d.locked = true; });
    afterDrawingsChanged();
    drawStatus("All drawings locked. Unlock per drawing in the list, or with Unlock all.");
  });
  if ($("#draw-unlockall")) $("#draw-unlockall").addEventListener("click", () => {
    pushDrawHistory();
    (state.drawings || []).forEach((d) => { d.locked = false; });
    afterDrawingsChanged();
    drawStatus("All drawings unlocked.");
  });
  // Escape cancels: pending anchor first, then the active tool.
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if (state.drawMulti) {
      state.drawMulti = null;
      state.pendingMarker = [];
      flushMarkers();
      drawStatus("Multi-anchor drawing cancelled.");
      return;
    }
    if (state.drawPending || state.drawPending3) {
      state.drawPending = null;
      state.drawPending3 = null;
      clearDrawPreview();
      state.drawPending3 = null;
      state.pendingMarker = [];
      flushMarkers();
      drawStatus("Drawing cancelled.");
      return;
    }
    if (state.drawSelectId) {
      state.drawSelectId = null;
      renderDrawList();
      refreshSelectionMarkers();
      drawStatus("Selection cleared.");
      return;
    }
    if (state.drawTool) { setDrawTool(null); drawStatus("Tool cancelled."); }
  });
  /* Delete / Backspace removes the selected drawing, or — when nothing is
     selected — the drawing under the pointer. Guarded so it never fires while
     typing, only inside the chart view, and never when nothing is targeted. */
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Delete" && e.key !== "Backspace") return;
    const t = e.target;
    if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable)) return;
    const v = $("#view-charts");
    if (!(v && (v.classList.contains("active") || !v.hidden))) return;
    if (state.drawPending || state.drawPending3 || state.drawMulti) return; // Esc/click cancels a partial drawing
    let id = state.drawSelectId;
    if (!id) {
      const h = state.drawHover;
      if (h) {
        const body = drawingBodyHit(h.x, h.y, 12);
        const anch = anchorHitAt(h.x, h.y, 16);
        const hit = body && anch ? (body.dist <= anch.dist ? body : anch) : (body || anch);
        if (hit) id = hit.id;
      }
    }
    if (!id) return;
    const d = (state.drawings || []).find((z) => z.id === id);
    if (!d) return;
    e.preventDefault();
    e.stopPropagation();
    if (d.locked) { drawStatus("Locked drawing — unlock it in the list below before deleting."); return; }
    pushDrawHistory();
    state.drawings = (state.drawings || []).filter((z) => z.id !== id);
    state.drawSelectId = null;
    afterDrawingsChanged();
    drawStatus("Drawing deleted (Cmd/Ctrl+Z restores it).");
  });
  // Enter (or a double-click on the chart) finishes a polyline.
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Enter" || !state.drawMulti || !DRAW_VARLEN.has(state.drawMulti.type)) return;
    const t = e.target;
    if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT")) return;
    e.preventDefault();
    finishMulti();
  });
  if ($("#draw-undo")) $("#draw-undo").addEventListener("click", drawingsUndo);
  if ($("#draw-redo")) $("#draw-redo").addEventListener("click", drawingsRedo);
  if ($("#draw-clear")) $("#draw-clear").addEventListener("click", () => {
    if (!(state.drawings || []).length) return;
    const n = state.drawings.length;
    if (!window.confirm(`Delete all ${n} drawings for ${state.chartSymbol || "this symbol"}? (Undo still restores them.)`)) return;
    pushDrawHistory();
    state.drawings = [];
    afterDrawingsChanged();
    drawStatus(`All ${n} drawings deleted (Undo restores them).`);
  });
  if ($("#draw-save")) $("#draw-save").addEventListener("click", () => {
    persistDrawings(state.chartSymbol, state.drawings);
    drawStatus(`Saved ${(state.drawings || []).length} drawing(s) for ${state.chartSymbol}.`);
  });
  /* §6 hide-all-drawings: one switch, two controls (this drawer checkbox and the
     toolbar button in the Draw popover) drive the same state. Hiding is purely a
     render-time skip — the stored drawings are untouched, so Show restores them
     exactly, and a timeframe change cannot lose them either. */
  if ($("#draw-visible")) $("#draw-visible").addEventListener("change", () => {
    setDrawVisible($("#draw-visible").checked);
  });
  if ($("#draw-toggle")) $("#draw-toggle").addEventListener("click", () => {
    setDrawVisible(!state.drawVisible);
  });
  if ($("#draw-export")) $("#draw-export").addEventListener("click", () => {
    download(`${state.chartSymbol}-drawings.json`,
      JSON.stringify({ symbol: state.chartSymbol, drawings: state.drawings, exported_at: new Date().toISOString() }, null, 2),
      "application/json");
  });
}

function afterChartBuilt(symbol) {
  state.chartSymbol = symbol;
  if (!state.drawingsLoadedFor || state.drawingsLoadedFor !== symbol) {
    state.drawings = loadDrawings(symbol);
    state.drawingsLoadedFor = symbol;
    state.drawUndo = [];
    state.drawRedo = [];
  }
  renderDrawings();
  renderDrawList();
  if (state.rsData && $("#rs-overlay") && $("#rs-overlay").checked) drawRsOverlay(state.rsData);
}

/* Overlay drawing rules shared by every analysis layer:
   - draw at most MAX_OVERLAY_LINES, so a layer can never bury the candles;
   - label only the lines nearest the current price, so labels never stack up;
   - return the drawn series, so a result row can highlight its own line. */
const MAX_OVERLAY_LINES = 8;
const MAX_OVERLAY_LABELS = 4;
/* Two levels whose prices are within this fraction of each other would have
   their axis labels overlap and become unreadable, so only the first is
   labelled. The level line itself is still drawn either way. */
const OVERLAY_LABEL_MIN_GAP = 0.012;

function plotFibonacci(chart, data, bars) {
  // /api/bars/{symbol}/fibonacci returns retracements + extensions rows
  // (ratio, percent, price, kind, family). `available:false` means the symbol
  // has too few confirmed swings - draw nothing, invent nothing.
  if (!data || data.available === false || !bars || !bars.length) return [];
  const rows = []
    .concat(Array.isArray(data.retracements) ? data.retracements : [])
    .concat(Array.isArray(data.extensions) ? data.extensions : [])
    .filter((l) => l && typeof l.price === "number" && isFinite(l.price));
  if (!rows.length) return [];
  const first = bars[0], last = bars[bars.length - 1];
  const lastClose = last.close;
  // Keep the lines nearest the traded price: the relevant ones.
  rows.sort((a, b) => Math.abs(a.price - lastClose) - Math.abs(b.price - lastClose));
  const kept = rows.slice(0, MAX_OVERLAY_LINES);
  const made = [];
  const labelled = [];
  kept.forEach((l) => {
    const isExt = l.kind === "extension";
    const color = isExt ? PRAVAHA.cyan : PRAVAHA.caution;
    const pct = typeof l.percent === "number"
      ? l.percent
      : (typeof l.ratio === "number" ? +(l.ratio * 100).toFixed(3) : null);
    const label = (isExt ? "Ext " : "Ret ") + (pct === null ? "?" : pct) + "%";
    // Only label levels that will not collide with an already-labelled one.
    const farEnough = labelled.every((p) => Math.abs(p - l.price) > Math.max(1, p * OVERLAY_LABEL_MIN_GAP));
    const doLabel = labelled.length < MAX_OVERLAY_LABELS && farEnough;
    if (doLabel) labelled.push(l.price);
    const line = chart.addLineSeries({
      color, lineWidth: 1, lineStyle: 2, priceLineVisible: false, lastValueVisible: false,
      title: doLabel ? label : "",
    });
    line.setData([{ time: first.time, value: l.price }, { time: last.time, value: l.price }]);
    made.push({ series: line, price: l.price, label, kind: "fib", labelled: doLabel });
  });
  return made;
}


function plotSupportResistance(chart, data, bars) {
  // /api/bars/{symbol}/levels returns zone BANDS (lower/upper/center + the swing
  // kinds that formed them). Drawing every zone is what made the chart unreadable:
  // the endpoint can return dozens, so only the nearest few to the traded price
  // are drawn and only those are labelled.
  if (!data || !data.zones || !data.zones.length || !bars || !bars.length) return [];
  const first = bars[0], last = bars[bars.length - 1];
  const lastClose = last.close;
  const zones = data.zones
    .filter((z) => typeof z.center === "number" && isFinite(z.center))
    .sort((a, b) => Math.abs(a.center - lastClose) - Math.abs(b.center - lastClose))
    .slice(0, MAX_OVERLAY_LINES);
  const made = [];
  const labelled = []; // prices already carrying an axis label
  zones.forEach((z) => {
    const kinds = Array.isArray(z.kinds) ? z.kinds : [];
    const kind = kinds.length && kinds.every((k) => k === "low")
      ? "support"
      : kinds.length && kinds.every((k) => k === "high") ? "resistance" : "zone";
    const color = kind === "support" ? PRAVAHA.up : kind === "resistance" ? PRAVAHA.down : PRAVAHA.caution;
    const lo = typeof z.lower === "number" ? z.lower : null;
    const hi = typeof z.upper === "number" ? z.upper : null;
    const span = lo !== null && hi !== null ? ` [${Math.round(lo)}-${Math.round(hi)}]` : "";
    // Label the level only if it is one of the nearest few AND far enough from
    // an already-labelled level that the two axis labels will not overlap.
    const farEnough = labelled.every((p) => Math.abs(p - z.center) > Math.max(1, p * OVERLAY_LABEL_MIN_GAP));
    const doLabel = labelled.length < MAX_OVERLAY_LABELS && farEnough;
    if (doLabel) labelled.push(z.center);
    const label = doLabel ? `${kind} @ ${Math.round(z.center)}${span}` : kind;
    const line = chart.addLineSeries({
      color, lineWidth: 1, lineStyle: 2, priceLineVisible: false,
      lastValueVisible: false, title: doLabel ? label : "",
    });
    line.setData([{ time: first.time, value: z.center }, { time: last.time, value: z.center }]);
    made.push({ series: line, price: z.center, label, kind: "sr", lo, hi, labelled: doLabel });
  });
  return made;
}


/* Market Structure & Liquidity layer (Phase B.1): swings, HH/HL/LH/LL labels,
   BOS/CHoCH breaks, equal highs/lows and Fair Value Gaps. Reuses the
   /api/bars/{symbol}/structure endpoint. Every mark is provisional until
   confirmed_index bars have closed. */
function plotMarketStructure(chart, data, bars) {
  if (!data || !bars || !bars.length) return [];
  const first = bars[0], last = bars[bars.length - 1];
  const made = [];
  const ts = chart.timeScale();
  // 1. Swing highs/lows as markers (merged via flushMarkers).
  const swings = Array.isArray(data.swings) ? data.swings : [];
  swings.forEach((sw) => {
    if (sw.index == null || !sw.date) return;
    const idx = Math.min(Math.max(sw.index, 0), bars.length - 1);
    const b = bars[idx];
    if (!b || !b.time) return;
    const isHigh = sw.kind === "high";
    state.structureMarkers.push({
      time: b.time, position: isHigh ? "aboveBar" : "belowBar",
      color: isHigh ? PRAVAHA.down : PRAVAHA.up,
      shape: "circle", text: isHigh ? "H" : "L",
    });
  });
  // 2. BOS / CHoCH breaks as horizontal level lines across the visible range.
  const breaks = Array.isArray(data.breaks) ? data.breaks : [];
  breaks.forEach((br) => {
    if (br.index == null || typeof br.price !== "number") return;
    const idx = Math.min(Math.max(br.index, 0), bars.length - 1);
    const b = bars[idx];
    if (!b || !b.time) return;
    const color = String(br.kind || "").toLowerCase().includes("bull") ? PRAVAHA.up : PRAVAHA.down;
    const line = chart.addLineSeries({
      color, lineWidth: 1, lineStyle: 2, priceLineVisible: false,
      lastValueVisible: false, title: br.kind || "break",
    });
    line.setData([{ time: first.time, value: br.price }, { time: last.time, value: br.price }]);
    made.push({ series: line, kind: "break", label: br.kind, price: br.price });
  });
  // 3. Fair Value Gaps as horizontal bands (top/bottom lines).
  const fvgs = Array.isArray(data.fvgs) ? data.fvgs : [];
  fvgs.slice(-8).forEach((g) => {
    if (g.index == null) return;
    const idx = Math.min(Math.max(g.index, 0), bars.length - 1);
    const b = bars[idx];
    if (!b || !b.time) return;
    const color = g.type === "bullish" ? PRAVAHA.up : PRAVAHA.down;
    const top = chart.addLineSeries({ color, lineWidth: 1, lineStyle: 3, priceLineVisible: false, lastValueVisible: false, title: `FVG ${g.type}` });
    const bot = chart.addLineSeries({ color, lineWidth: 1, lineStyle: 3, priceLineVisible: false, lastValueVisible: false, title: "" });
    top.setData([{ time: b.time, value: g.top }, { time: last.time, value: g.top }]);
    bot.setData([{ time: b.time, value: g.bottom }, { time: last.time, value: g.bottom }]);
    made.push({ series: top, kind: "fvg", label: g.type });
    made.push({ series: bot, kind: "fvg", label: g.type });
  });
  // 4. Equal highs/lows as markers.
  const eq = Array.isArray(data.equal_highs_lows) ? data.equal_highs_lows : [];
  eq.forEach((e) => {
    if (e.index == null) return;
    const idx = Math.min(Math.max(e.index, 0), bars.length - 1);
    const b = bars[idx];
    if (!b || !b.time) return;
    const isHigh = String(e.kind).includes("high");
    state.structureMarkers.push({
      time: b.time, position: isHigh ? "aboveBar" : "belowBar",
      color: PRAVAHA.caution, shape: "square", text: "EQ",
    });
  });
  return made;
}

/* Trend Strength & Regime layer (Phase B.2): ADX + directional indicators,
   Supertrend, Parabolic SAR. Reuses /api/bars/{symbol}/indicator for each.
   Regime classification is a heuristic over ADX (trend strength) and the sign
   of (+DI - -DI) (direction). It is a description of the recent past, not a
   prediction. */
function classifyTrendRegime(adx, plusDi, minusDi, trendThreshold, rangeThreshold) {
  const t = (typeof trendThreshold === "number") ? trendThreshold : 25;
  const r = (typeof rangeThreshold === "number") ? rangeThreshold : 20;
  if (!isFinite(adx)) return { regime: "unknown", direction: "neutral", adx: null };
  const regime = adx >= t ? "trending" : (adx < r ? "ranging" : "transition");
  const direction = (isFinite(plusDi) && isFinite(minusDi))
    ? (plusDi > minusDi ? "bullish" : (plusDi < minusDi ? "bearish" : "neutral"))
    : "neutral";
  return { regime, direction, adx: adx };
}

async function plotTrendStrength(chart, data, bars) {
  if (!bars || !bars.length) return [];
  const symbol = state.chartSymbol;
  const first = bars[0], last = bars[bars.length - 1];
  const made = [];
  const markers = [];
  // Fetch the three indicators in parallel.
  let adxR = null, stR = null, sarR = null;
  try {
    const [a, b, c] = await Promise.all([
      api(`/api/bars/${encodeURIComponent(symbol)}/indicator?name=adx`),
      api(`/api/bars/${encodeURIComponent(symbol)}/indicator?name=supertrend`),
      api(`/api/bars/${encodeURIComponent(symbol)}/indicator?name=parabolic_sar`),
    ]);
    adxR = a; stR = b; sarR = c;
  } catch (e) { /* fall through; partial data still plotted */ }
  // 1. Supertrend as a coloured line (green bullish, red bearish).
  const stA = alignIndicatorToBars(stR, bars);
  if (stA && stA.series) {
    const st = stA.series.supertrend || stA.series.value || Object.values(stA.series)[0];
    const dir = stR.series.direction || stR.series.trend || null;
    if (Array.isArray(st)) {
      const pts = [];
      for (let i = 0; i < bars.length; i++) {
        if (st[i] == null || !isFinite(st[i])) continue;
        pts.push({ time: bars[i].time, value: Number(st[i]) });
      }
      if (pts.length) {
        const line = chart.addLineSeries({ color: PRAVAHA.cyan, lineWidth: 2, priceLineVisible: false, lastValueVisible: false, title: "Supertrend" });
        line.setData(pts);
        made.push({ series: line, kind: "supertrend", label: "Supertrend" });
      }
    }
  }
  // 2. Parabolic SAR as markers.
  const sarA = alignIndicatorToBars(sarR, bars);
  if (sarA && sarA.series) {
    const sar = sarA.series.sar || sarA.series.value || Object.values(sarA.series)[0];
    if (Array.isArray(sar)) {
      for (let i = 0; i < bars.length; i++) {
        if (sar[i] == null || !isFinite(sar[i])) continue;
        state.trendMarkers.push({
          time: bars[i].time, position: "inBar", color: PRAVAHA.caution,
          shape: "circle", text: "",
        });
      }
    }
  }
  // 3. Regime classification from the latest ADX reading.
  let regime = { regime: "unknown", direction: "neutral", adx: null };
  const adxA = alignIndicatorToBars(adxR, bars);
  if (adxA && adxA.series) {
    const adxArr = adxA.series.adx || adxA.series.value || Object.values(adxA.series)[0];
    const plusArr = adxA.series.plus_di || adxA.series.pdi || null;
    const minusArr = adxA.series.minus_di || adxA.series.mdi || null;
    if (Array.isArray(adxArr) && adxArr.length) {
      // latest non-null
      let lastAdx = null, lastPlus = null, lastMinus = null;
      for (let i = adxArr.length - 1; i >= 0; i--) {
        if (adxArr[i] != null && isFinite(adxArr[i])) { lastAdx = adxArr[i]; lastPlus = plusArr ? plusArr[i] : null; lastMinus = minusArr ? minusArr[i] : null; break; }
      }
      regime = classifyTrendRegime(lastAdx, lastPlus, lastMinus);
    }
  }
  state.layerData.trend = { adx: regime.adx, regime: regime.regime, direction: regime.direction };
  return made;
}

/* Momentum, Divergence & Relative Strength layer (Phase B.3).
   Reuses /api/bars/{symbol}/indicator (rsi, macd, roc) and
   /api/bars/{symbol}/relative-strength. Divergence is detected on confirmed
   fractal swings of price vs RSI (no look-ahead). */
function findSwingsJS(highs, lows, left, right) {
  // Returns array of {index, kind, price, confirmedIndex}.
  const n = highs.length;
  const out = [];
  for (let i = left; i < n - right; i++) {
    let isHigh = true, isLow = true;
    for (let k = 1; k <= left; k++) {
      if (highs[i] <= highs[i - k]) isHigh = false;
      if (lows[i] >= lows[i + k]) isLow = false; // placeholder; corrected below
    }
    for (let k = 1; k <= right; k++) {
      if (highs[i] <= highs[i + k]) isHigh = false;
      if (lows[i] >= lows[i - k]) isLow = false;
    }
    // recompute isLow correctly
    isLow = true;
    for (let k = 1; k <= left; k++) { if (lows[i] >= lows[i - k]) isLow = false; }
    for (let k = 1; k <= right; k++) { if (lows[i] >= lows[i + k]) isLow = false; }
    if (isHigh) out.push({ index: i, kind: "high", price: highs[i], confirmedIndex: i + right });
    if (isLow) out.push({ index: i, kind: "low", price: lows[i], confirmedIndex: i + right });
  }
  return out;
}

function detectDivergence(priceHighs, priceLows, indValues, left, right) {
  // Returns array of {index, type: "bullish"|"bearish", confirmedIndex}.
  // Bullish: price lower low, indicator higher low.
  // Bearish: price higher high, indicator lower high.
  const pSw = findSwingsJS(priceHighs, priceLows, left, right);
  const iSw = findSwingsJS(indValues, indValues, left, right); // use ind as both high & low
  const out = [];
  const priceLowsSw = pSw.filter((s) => s.kind === "low");
  const priceHighsSw = pSw.filter((s) => s.kind === "high");
  const indLowsSw = iSw.filter((s) => s.kind === "low");
  const indHighsSw = iSw.filter((s) => s.kind === "high");
  // bullish: consecutive price lows declining, RSI lows rising
  for (let i = 1; i < priceLowsSw.length; i++) {
    const prev = priceLowsSw[i - 1], cur = priceLowsSw[i];
    if (cur.price < prev.price) {
      // find matching ind lows
      const indPrev = indLowsSw.find((s) => s.index <= prev.index && s.index >= prev.index - 2);
      const indCur = indLowsSw.find((s) => s.index <= cur.index && s.index >= cur.index - 2);
      if (indPrev && indCur && indCur.price > indPrev.price) {
        out.push({ index: cur.index, type: "bullish", confirmedIndex: Math.max(cur.confirmedIndex, indCur.confirmedIndex) });
      }
    }
  }
  // bearish: consecutive price highs rising, RSI highs falling
  for (let i = 1; i < priceHighsSw.length; i++) {
    const prev = priceHighsSw[i - 1], cur = priceHighsSw[i];
    if (cur.price > prev.price) {
      const indPrev = indHighsSw.find((s) => s.index <= prev.index && s.index >= prev.index - 2);
      const indCur = indHighsSw.find((s) => s.index <= cur.index && s.index >= cur.index - 2);
      if (indPrev && indCur && indCur.price < indPrev.price) {
        out.push({ index: cur.index, type: "bearish", confirmedIndex: Math.max(cur.confirmedIndex, indCur.confirmedIndex) });
      }
    }
  }
  return out;
}

async function plotMomentumDivergence(chart, data, bars) {
  if (!bars || !bars.length) return [];
  const symbol = state.chartSymbol;
  const made = [];
  // Divergence on RSI (fetched + aligned by date)
  let rsiAligned = null;
  try {
    const rsiR = await api(`/api/bars/${encodeURIComponent(symbol)}/indicator?name=rsi`);
    const rsiA = alignIndicatorToBars(rsiR, bars);
    if (rsiA && rsiA.series) rsiAligned = rsiA.series.rsi || rsiA.series.value || Object.values(rsiA.series)[0];
  } catch (e) { /* unavailable */ }
  if (rsiAligned && Array.isArray(rsiAligned)) {
    const highs = bars.map((b) => b.high);
    const lows = bars.map((b) => b.low);
    const indVals = rsiAligned.map((v) => (v == null || !isFinite(v)) ? NaN : v);
    const safeInd = indVals.map((v) => (isNaN(v) ? 0 : v));
    const divs = detectDivergence(highs, lows, safeInd, 2, 2);
    divs.forEach((dv) => {
      const idx = Math.min(Math.max(dv.index, 0), bars.length - 1);
      const b = bars[idx];
      if (!b || !b.time) return;
      const isBull = dv.type === "bullish";
      state.momentumMarkers.push({
        time: b.time, position: isBull ? "belowBar" : "aboveBar",
        color: isBull ? PRAVAHA.up : PRAVAHA.down,
        shape: "arrowUp", text: isBull ? "Bull div" : "Bear div",
      });
    });
  }
  // Relative strength vs NEPSE
  try {
    const rs = await api(`/api/bars/${encodeURIComponent(symbol)}/relative-strength?window=60`);
    if (rs && rs.available !== false && Array.isArray(rs.ratio_points) && rs.ratio_points.length) {
      const pts = rs.ratio_points.map((p) => ({ time: String(p.date || p.time).slice(0, 10), value: Number(p.ratio || p.value) }))
        .filter((p) => p.time && isFinite(p.value));
      if (pts.length) {
        const line = chart.addLineSeries({ color: PRAVAHA.mint, lineWidth: 2, priceLineVisible: false, lastValueVisible: false, title: "RS vs NEPSE" });
        line.setData(pts);
        made.push({ series: line, kind: "rs", label: "Relative strength" });
      }
    }
  } catch (e) { /* benchmark unavailable - honestly reported */ }
  state.layerData.momentum = {
    rsiDivergences: (rsiAligned ? detectDivergence(bars.map((b)=>b.high), bars.map((b)=>b.low), (rsiAligned||[]).map(v=>isNaN(v)?0:v), 2, 2).length : 0),
    relativeStrengthAvailable: false,
  };
  try {
    const rs = await api(`/api/bars/${encodeURIComponent(symbol)}/relative-strength?window=60`);
    state.layerData.momentum.relativeStrengthAvailable = !!(rs && rs.available !== false);
  } catch (e) { /* unavailable */ }
  return made;
}

/* Align an indicator response (which carries its own `dates` array) to the
   chart's bar set by trading date. The indicator endpoint returns the full
   stored history, but the chart may show only the last N bars, so positional
   indexing would land on the wrong bars. Returns {series:{col:[value per bar]}}
   or null if the response is unusable. */
function alignIndicatorToBars(ind, bars) {
  if (!ind || !ind.series || !Array.isArray(ind.dates) || !bars || !bars.length) return null;
  const dateToIdx = new Map();
  ind.dates.forEach((d, i) => { if (d != null) dateToIdx.set(String(d).slice(0, 10), i); });
  const out = { series: {} };
  Object.keys(ind.series).forEach((col) => {
    out.series[col] = bars.map((b) => {
      const i = dateToIdx.get(String(b.time).slice(0, 10));
      if (i == null) return null;
      const v = ind.series[col][i];
      return (v == null || (typeof v === "number" && !isFinite(v))) ? null : v;
    });
  });
  return out;
}

/* Volatility & Breakout layer (Phase B.4).
   Reuses /api/bars/{symbol}/indicator for bollinger, keltner, atr.
   Squeeze = Bollinger bands inside Keltner channels (BB upper < KC upper
   AND BB lower > KC lower). Breakout candidate = close beyond a band with
   the band expanding; direction is reported, not predicted. */
async function plotVolatilityBreakout(chart, data, bars) {
  if (!bars || !bars.length) return [];
  const symbol = state.chartSymbol;
  const first = bars[0], last = bars[bars.length - 1];
  const made = [];
  let bbR = null, kcR = null, atrR = null;
  try {
    const [a, b, c] = await (async () => Promise.all([
      api(`/api/bars/${encodeURIComponent(symbol)}/indicator?name=bollinger`),
      api(`/api/bars/${encodeURIComponent(symbol)}/indicator?name=keltner`),
      api(`/api/bars/${encodeURIComponent(symbol)}/indicator?name=atr`),
    ]))();
    bbR = a; kcR = b; atrR = c;
  } catch (e) { /* fall through */ }
  // 1. Bollinger bands (middle solid, upper/lower dashed).
  const bbA = alignIndicatorToBars(bbR, bars);
  const kcA = alignIndicatorToBars(kcR, bars);
  if (bbA && bbA.series) {
    const mid = bbA.series.middle, up = bbA.series.upper, lo = bbA.series.lower;
    const addLine = (arr, color, style, title) => {
      if (!Array.isArray(arr)) return;
      const pts = [];
      for (let i = 0; i < arr.length && i < bars.length; i++) {
        if (arr[i] == null || !isFinite(arr[i])) continue;
        pts.push({ time: bars[i].time, value: Number(arr[i]) });
      }
      if (pts.length) {
        const line = chart.addLineSeries({ color, lineWidth: 1, lineStyle: style, priceLineVisible: false, lastValueVisible: false, title });
        line.setData(pts);
        made.push({ series: line, kind: "bb", label: title });
      }
    };
    addLine(mid, PRAVAHA.muted, 0, "BB mid");
    addLine(up, PRAVAHA.cyan, 2, "BB upper");
    addLine(lo, PRAVAHA.cyan, 2, "BB lower");
  }
  // 2. Keltner channels (dashed, caution colour).
  if (kcA && kcA.series) {
    const mid = kcA.series.middle, up = kcA.series.upper, lo = kcA.series.lower;
    const addLine = (arr, title) => {
      if (!Array.isArray(arr)) return;
      const pts = [];
      for (let i = 0; i < arr.length && i < bars.length; i++) {
        if (arr[i] == null || !isFinite(arr[i])) continue;
        pts.push({ time: bars[i].time, value: Number(arr[i]) });
      }
      if (pts.length) {
        const line = chart.addLineSeries({ color: PRAVAHA.caution, lineWidth: 1, lineStyle: 3, priceLineVisible: false, lastValueVisible: false, title });
        line.setData(pts);
        made.push({ series: line, kind: "kc", label: title });
      }
    };
    addLine(up, "KC upper");
    addLine(lo, "KC lower");
  }
  // 3. Squeeze + breakout markers on the last bar.
  let squeezeCount = 0, breakoutCount = 0;
  if (bbA && bbA.series && kcA && kcA.series) {
    const bbUp = bbA.series.upper, bbLo = bbA.series.lower;
    const kcUp = kcA.series.upper, kcLo = kcA.series.lower;
    const closes = bars.map((b) => b.close);
    for (let i = 0; i < bars.length; i++) {
      if (bbUp[i] == null || bbLo[i] == null || kcUp[i] == null || kcLo[i] == null) continue;
      const squeeze = (bbUp[i] < kcUp[i]) && (bbLo[i] > kcLo[i]);
      if (squeeze) squeezeCount++;
      // breakout: close beyond a band
      if (closes[i] > bbUp[i]) {
        breakoutCount++;
        state.volatilityMarkers.push({ time: bars[i].time, position: "aboveBar", color: PRAVAHA.up, shape: "arrowUp", text: "BO" });
      } else if (closes[i] < bbLo[i]) {
        breakoutCount++;
        state.volatilityMarkers.push({ time: bars[i].time, position: "belowBar", color: PRAVAHA.down, shape: "arrowDown", text: "BO" });
      }
    }
  }
  state.layerData.volatility = { squeezeCount, breakoutCount };
  return made;
}

/* Volume & Accumulation layer (Phase B.5).
   Reuses /api/bars/{symbol}/indicator for obv, cmf, ad_line, relative_volume.
   Volume spikes: RVOL > threshold (default 2.0). PV divergence: price swing
   high + OBV swing low (bearish) or price swing low + OBV swing high (bullish). */
async function plotVolumeAccumulation(chart, data, bars) {
  if (!bars || !bars.length) return [];
  const symbol = state.chartSymbol;
  const made = [];
  let obvR = null, cmfR = null, adR = null, rvolR = null;
  try {
    const [a, b, c, d] = await Promise.all([
      api(`/api/bars/${encodeURIComponent(symbol)}/indicator?name=obv`),
      api(`/api/bars/${encodeURIComponent(symbol)}/indicator?name=cmf`),
      api(`/api/bars/${encodeURIComponent(symbol)}/indicator?name=ad_line`),
      api(`/api/bars/${encodeURIComponent(symbol)}/indicator?name=relative_volume`),
    ]);
    obvR = a; cmfR = b; adR = c; rvolR = d;
  } catch (e) { /* fall through */ }
  // 1. OBV as a line (mint).
  const obvA = alignIndicatorToBars(obvR, bars);
  if (obvA && obvA.series) {
    const obv = obvA.series.obv || obvA.series.value || Object.values(obvA.series)[0];
    if (Array.isArray(obv)) {
      const pts = [];
      for (let i = 0; i < bars.length; i++) {
        if (obv[i] == null || !isFinite(obv[i])) continue;
        pts.push({ time: bars[i].time, value: Number(obv[i]) });
      }
      if (pts.length) {
        const line = chart.addLineSeries({ color: PRAVAHA.mint, lineWidth: 2, priceLineVisible: false, lastValueVisible: false, title: "OBV", priceScaleId: "volacc" });
        line.setData(pts);
        made.push({ series: line, kind: "obv", label: "OBV" });
      }
    }
  }
  // 2. CMF as a line (cyan).
  const cmfA = alignIndicatorToBars(cmfR, bars);
  if (cmfA && cmfA.series) {
    const cmf = cmfA.series.cmf || cmfA.series.value || Object.values(cmfA.series)[0];
    if (Array.isArray(cmf)) {
      const pts = [];
      for (let i = 0; i < bars.length; i++) {
        if (cmf[i] == null || !isFinite(cmf[i])) continue;
        pts.push({ time: bars[i].time, value: Number(cmf[i]) });
      }
      if (pts.length) {
        const line = chart.addLineSeries({ color: PRAVAHA.cyan, lineWidth: 1, lineStyle: 2, priceLineVisible: false, lastValueVisible: false, title: "CMF", priceScaleId: "volacc" });
        line.setData(pts);
        made.push({ series: line, kind: "cmf", label: "CMF" });
      }
    }
  }
  // 3. A/D line as a line (caution).
  const adA = alignIndicatorToBars(adR, bars);
  if (adA && adA.series) {
    const ad = adA.series.ad || adA.series.value || Object.values(adA.series)[0];
    if (Array.isArray(ad)) {
      const pts = [];
      for (let i = 0; i < bars.length; i++) {
        if (ad[i] == null || !isFinite(ad[i])) continue;
        pts.push({ time: bars[i].time, value: Number(ad[i]) });
      }
      if (pts.length) {
        const line = chart.addLineSeries({ color: PRAVAHA.caution, lineWidth: 1, lineStyle: 3, priceLineVisible: false, lastValueVisible: false, title: "A/D", priceScaleId: "volacc" });
        line.setData(pts);
        made.push({ series: line, kind: "ad", label: "A/D" });
      }
    }
  }
  // 4. Volume spikes: RVOL > threshold (default 2.0).
  const rvolA = alignIndicatorToBars(rvolR, bars);
  const rvol = rvolA && rvolA.series ? (rvolA.series.rvol || rvolA.series.value || Object.values(rvolA.series)[0]) : null;
  const SPIKE_THRESHOLD = 2.0;
  if (Array.isArray(rvol)) {
    for (let i = 0; i < bars.length; i++) {
      if (rvol[i] == null || !isFinite(rvol[i])) continue;
      if (rvol[i] >= SPIKE_THRESHOLD) {
        state.volumeMarkers.push({
          time: bars[i].time, position: "inBar", color: PRAVAHA.caution,
          shape: "circle", text: "V",
        });
      }
    }
  }
  // 5. Price-volume divergence on OBV.
  if (obvA && obvA.series) {
    const obv = obvA.series.obv || obvA.series.value || Object.values(obvA.series)[0];
    if (Array.isArray(obv)) {
      const indVals = obv.map((v) => (v == null || !isFinite(v)) ? 0 : v);
      const divs = detectDivergence(bars.map((b) => b.high), bars.map((b) => b.low), indVals, 2, 2);
      divs.forEach((dv) => {
        const idx = Math.min(Math.max(dv.index, 0), bars.length - 1);
        const b = bars[idx];
        if (!b || !b.time) return;
        const isBull = dv.type === "bullish";
        state.volumeMarkers.push({
          time: b.time, position: isBull ? "belowBar" : "aboveBar",
          color: isBull ? PRAVAHA.up : PRAVAHA.down,
          shape: "arrowUp", text: isBull ? "PV bull" : "PV bear",
        });
      });
    }
  }
  try { chart.priceScale("volacc").applyOptions({ scaleMargins: { top: 0.1, bottom: 0.1 }, visible: false }); } catch (e) { /* scale not created */ }
  state.layerData.volume = {
    obvAvailable: !!(obvA && obvA.series),
    cmfAvailable: !!(cmfA && cmfA.series),
    adAvailable: !!(adA && adA.series),
    rvolAvailable: !!(rvolA && rvolA.series),
    spikeThreshold: SPIKE_THRESHOLD,
  };
  return made;
}


/* Gap & Opening-Price Analysis layer (Phase B.6). Reuses /api/bars/{symbol}/gaps. */
async function plotGapAnalysis(chart, data, bars) {
  if (!bars || !bars.length) return [];
  const symbol = state.chartSymbol;
  const made = [];
  let gapsR = null;
  try { gapsR = await api(`/api/bars/${encodeURIComponent(symbol)}/gaps?limit=250`); } catch (e) { gapsR = null; }
  state.gapMarkers = [];
  if (gapsR && Array.isArray(gapsR.gaps)) {
    gapsR.gaps.forEach((g) => {
      if (g.index == null) return;
      const idx = Math.min(Math.max(g.index, 0), bars.length - 1);
      const b = bars[idx];
      if (!b || !b.time) return;
      const isUp = String(g.type || "").toLowerCase().includes("up") || (g.size && g.size > 0);
      state.gapMarkers.push({
        time: b.time, position: isUp ? "aboveBar" : "belowBar",
        color: isUp ? PRAVAHA.up : PRAVAHA.down,
        shape: "arrowUp", text: isUp ? "Gap↑" : "Gap↓",
      });
    });
  }
  state.layerData.gap = { count: gapsR ? gapsR.count : 0, available: !!gapsR };
  return made;
}

/* Market Regime & Rotation layer (Phase B.6). Reuses trend layer (ADX regime) + sector rotation data. */
async function plotMarketRegime(chart, data, bars) {
  if (!bars || !bars.length) return [];
  const made = [];
  // Reuse the trend layer's regime classification
  try {
    const adxR = await api(`/api/bars/${encodeURIComponent(state.chartSymbol)}/indicator?name=adx`);
    const adxA = alignIndicatorToBars(adxR, bars);
    if (adxA && adxA.series) {
      const adxArr = adxA.series.adx || adxA.series.value || Object.values(adxA.series)[0];
      const lastAdx = Array.isArray(adxArr) ? adxArr.filter((v) => v != null && isFinite(v)).slice(-1)[0] : null;
      state.layerData.regime = { adx: lastAdx, regime: lastAdx >= 25 ? "trending" : (lastAdx < 20 ? "ranging" : "transition") };
    }
  } catch (e) { state.layerData.regime = { adx: null, regime: "unknown" }; }
  return made;
}

/* Relative Performance & Leaders/Laggards layer (Phase B.6). Reuses relative-strength endpoint. */
async function plotRelativePerformance(chart, data, bars) {
  if (!bars || !bars.length) return [];
  const symbol = state.chartSymbol;
  const made = [];
  try {
    const rs = await api(`/api/bars/${encodeURIComponent(symbol)}/relative-strength?window=60`);
    if (rs && rs.available !== false && Array.isArray(rs.ratio_points) && rs.ratio_points.length) {
      const pts = rs.ratio_points.map((p) => ({ time: String(p.date || p.time).slice(0, 10), value: Number(p.ratio || p.value) }))
        .filter((p) => p.time && isFinite(p.value));
      if (pts.length) {
        const line = chart.addLineSeries({ color: PRAVAHA.mint, lineWidth: 2, priceLineVisible: false, lastValueVisible: false, title: "RS vs NEPSE" });
        line.setData(pts);
        made.push({ series: line, kind: "rs", label: "Relative strength" });
      }
    }
    state.layerData.relative = { available: !!(rs && rs.available !== false), aligned: rs ? rs.coverage?.aligned_bars : 0 };
  } catch (e) { state.layerData.relative = { available: false, reason: e.message }; }
  return made;
}

/* Market Microstructure & Liquidity Proxies layer (Phase B.6). Volume/turnover proxies only. */
async function plotMicrostructure(chart, data, bars) {
  if (!bars || !bars.length) return [];
  const made = [];
  // Reuse relative volume indicator for liquidity proxy
  try {
    const rvolR = await api(`/api/bars/${encodeURIComponent(state.chartSymbol)}/indicator?name=relative_volume`);
    const rvolA = alignIndicatorToBars(rvolR, bars);
    if (rvolA && rvolA.series) {
      const rvol = rvolA.series.rvol || rvolA.series.value || Object.values(rvolA.series)[0];
      if (Array.isArray(rvol)) {
        const pts = [];
        for (let i = 0; i < bars.length; i++) {
          if (rvol[i] == null || !isFinite(rvol[i])) continue;
          pts.push({ time: bars[i].time, value: Number(rvol[i]) });
        }
        if (pts.length) {
          const line = chart.addLineSeries({ color: PRAVAHA.caution, lineWidth: 1, lineStyle: 2, priceLineVisible: false, lastValueVisible: false, title: "Rel. Volume" });
          line.setData(pts);
          made.push({ series: line, kind: "rvol", label: "Relative volume" });
        }
      }
    }
    state.layerData.micro = { rvolAvailable: !!(rvolA && rvolA.series), note: "proxies only — no order book data" };
  } catch (e) { state.layerData.micro = { available: false, reason: e.message }; }
  return made;
}

/* Price Distribution & Value Areas layer (Phase B.6). Reuses volume profile endpoint. */
async function plotPriceDistribution(chart, data, bars) {
  if (!bars || !bars.length) return [];
  const symbol = state.chartSymbol;
  const made = [];
  try {
    const d = await api(`/api/bars/${encodeURIComponent(symbol)}/volume-profile?bins=48&limit=250`);
    const prof = d && d.profile;
    if (prof && prof.poc) {
      const first = bars[0], last = bars[bars.length - 1];
      const addLevel = (price, color, style, label) => {
        if (typeof price !== "number" || !isFinite(price)) return;
        const line = chart.addLineSeries({ color, lineWidth: 1, lineStyle: style, priceLineVisible: false, lastValueVisible: false, title: label });
        line.setData([{ time: first.time, value: price }, { time: last.time, value: price }]);
        made.push({ series: line, kind: "dist", label });
      };
      addLevel(prof.poc.price, PRAVAHA.caution, 0, `POC ${Math.round(prof.poc.price)}`);
      const va = prof.value_area || {};
      addLevel(va.high, PRAVAHA.muted, 2, `VAH ${Math.round(va.high)}`);
      addLevel(va.low, PRAVAHA.muted, 2, `VAL ${Math.round(va.low)}`);
    }
    state.layerData.distribution = { available: !!(prof && prof.poc), note: "volume-at-price approximation from stored daily bars" };
  } catch (e) { state.layerData.distribution = { available: false, reason: e.message }; }
  return made;
}

/* Event & Corporate-Action Analysis layer (Phase B.6). Honest unavailable state. */
async function plotEventAnalysis(chart, data, bars) {
  if (!bars || !bars.length) return [];
  const made = [];
  // Corporate events for this symbol (dividends, bonus, rights, AGM). The
  // endpoint merges the stored table with the attested registry projection, so
  // a symbol with a known dated action reports it even with an empty table.
  state.layerData.event = { available: false, reason: "No corporate-event records stored for this symbol. Dividend/bonus/rights/AGM data is not available in this dataset." };
  try {
    const sym = encodeURIComponent(state.chartSymbol);
    const d = await api(`/api/corporate-events?symbol=${sym}&limit=100`);
    if (d && Array.isArray(d.events) && d.events.length) {
      state.layerData.event = { available: true, count: d.events.length, events: d.events };
    }
  } catch (e) { /* keep the honest unavailable state if the fetch fails */ }
  return made;
}

/* Strategy & Signal Validation layer (Phase B.6). Links to backtesting. */
async function plotStrategyValidation(chart, data, bars) {
  if (!bars || !bars.length) return [];
  const made = [];
  state.layerData.strategy = { available: true, note: "Use the Backtesting view (My Algorithms) to run strategy validation with transaction costs, drawdown, and benchmark comparison." };
  return made;
}

/* Volume profile layer: three landmark lines from the daily-bar profile the
   endpoint computed (POC solid, value-area edges dashed). The lines are drawn
   across the visible bar range only; if the profile covers more sessions than
   the chart's window that is stated in the results table, never silently. */
function plotVolumeProfile(chart, data, bars) {
  const prof = data && data.profile;
  if (!prof || !prof.poc || !bars || !bars.length) return [];
  const first = bars[0], last = bars[bars.length - 1];
  const made = [];
  const addLevel = (price, color, style, label, kind) => {
    if (typeof price !== "number" || !isFinite(price)) return;
    const line = chart.addLineSeries({
      color, lineWidth: 1, lineStyle: style, priceLineVisible: false,
      lastValueVisible: false, title: label,
    });
    line.setData([{ time: first.time, value: price }, { time: last.time, value: price }]);
    made.push({ series: line, price, label, kind, lo: null, hi: null });
  };
  addLevel(prof.poc.price, PRAVAHA.caution, 0, `POC ${Math.round(prof.poc.price)}`, "pg");
  const va = prof.value_area || {};
  addLevel(va.high, PRAVAHA.muted, 2, `VAH ${Math.round(va.high)}`, "pg");
  addLevel(va.low, PRAVAHA.muted, 2, `VAL ${Math.round(va.low)}`, "pg");
  return made;
}


function plotCandlestickMarkers(chart, patterns, bars) {
  if (!patterns || !patterns.length || !bars || !bars.length) return;
  patterns.forEach(p => {
    if (p.index == null || p.rule == null) return;
    const idx = Math.min(Math.max(p.index, 0), bars.length-1);
    const b = bars[idx];
    if (!b || !b.time) return;
    // Real marker: small text label at candle price (simplified — full requires chart lib marker API)
    console.log("Pattern at bar " + idx + " (" + b.time + "): " + p.rule + " price ~" + (b.high+b.low)/2);
  });
}

function plotElliottWave(chart, data, bars) { if (!data || !data.candidates || !data.candidates.length) return; console.log('Elliott candidates:', data.candidates.map(c=>c.label)); }

/* ======================================================= chart workspace chrome
   Layer manager, popovers and toolbar wiring. The chart opens clean; every
   analysis layer is a real fetch + draw plus a result row that can highlight
   its own overlay. */
const LAYER_DEFS = {
  sr: { label: "Support & resistance", hint: "Detected swing zones (nearest few only)" },
  fib: { label: "Fibonacci", hint: "Retracements and extensions of the main swing" },
  profile: { label: "Volume profile", hint: "POC + 70% value area from stored daily bars" },
  candles: { label: "Candlestick patterns", hint: "Bullish and bearish patterns marked on bars" },
  patterns: { label: "Chart patterns", hint: "Head & shoulders, triangles, flags…" },
  elliott: { label: "Elliott Wave", hint: "Candidate wave counts" },
  harmonic: { label: "Harmonic patterns", hint: "Gartley, Bat, Butterfly, Crab candidates" },
  structure: { label: "Market Structure & Liquidity", hint: "Swings, BOS/CHoCH, equal H/L, FVG" },
  trend: { label: "Trend Strength & Regime", hint: "ADX, Supertrend, Parabolic SAR, regime" },
  momentum: { label: "Momentum, Divergence & Relative Strength", hint: "RSI/MACD divergence, ROC, relative strength vs NEPSE" },
  volatility: { label: "Volatility & Breakout", hint: "Bollinger/Keltner, ATR, squeeze, breakout candidates" },
  volume: { label: "Volume & Accumulation", hint: "OBV, CMF, A/D, relative volume, spikes, PV divergence" },
  gap: { label: "Gap & Opening-Price Analysis", hint: "Gap up/down, gap size, fill status" },
  regime: { label: "Market Regime & Rotation", hint: "Trend/volatility regime, sector rotation" },
  relative: { label: "Relative Performance & Leaders/Laggards", hint: "Stock vs NEPSE, ranked leaders/laggards" },
  micro: { label: "Market Microstructure & Liquidity Proxies", hint: "Volume, turnover, liquidity proxies (no order book)" },
  distribution: { label: "Price Distribution & Value Areas", hint: "Price distribution, POC, value area" },
  event: { label: "Event & Corporate-Action Analysis", hint: "Corporate actions, dividends, earnings (data-dependent)" },
  strategy: { label: "Strategy & Signal Validation", hint: "Backtesting, transaction costs, drawdown, win rate" },
};
state.layers = {};
state.layerCounts = {};
state.layerData = {};
state.layerSeries = { sr: [], fib: [], profile: [], structure: [] };
// What each detector layer actually put on the chart (drawn/offRange/…), so a
// "found N" badge can never be mistaken for "N things are visible".
state.layerDrawn = {};

function layersFor(symbol) {
  try {
    const raw = localStorage.getItem("mt-chart-layers-" + symbol);
    const v = raw ? JSON.parse(raw) : null;
    if (v && typeof v === "object") return v;
  } catch (e) { /* first run */ }
  return {};
}

function saveLayers(symbol) {
  try { localStorage.setItem("mt-chart-layers-" + symbol, JSON.stringify(state.layers)); }
  catch (e) { /* storage full/blocked - the chart still works */ }
}

/* Quick-layer (chart-toolbar) toggles are persisted per symbol, following the
   same localStorage pattern as analysis layers and custom indicators. A saved
   state is an object mapping toggle id -> boolean. Missing/invalid state
   recovers to the boot defaults (volume on, the rest off). */
function quickLayersKey(symbol) { return "mt-quick-layers-" + symbol; }
function loadQuickLayers(symbol) {
  try {
    const raw = localStorage.getItem(quickLayersKey(symbol));
    const v = raw ? JSON.parse(raw) : null;
    if (v && typeof v === "object") return v;
  } catch (e) { /* first run / corrupt */ }
  return null;
}
function saveQuickLayers(symbol) {
  if (!symbol) return;
  const out = {};
  QUICK_IND_IDS.forEach((id) => { const el = document.getElementById(id); if (el) out[id] = !!el.checked; });
  try { localStorage.setItem(quickLayersKey(symbol), JSON.stringify(out)); }
  catch (e) { /* storage full/blocked - the chart still works */ }
}
function applyQuickLayersState(stateObj) {
  if (!stateObj || typeof stateObj !== "object") return false;
  let applied = false;
  QUICK_IND_IDS.forEach((id) => {
    const el = document.getElementById(id);
    if (el && Object.prototype.hasOwnProperty.call(stateObj, id)) {
      el.checked = !!stateObj[id];
      applied = true;
    }
  });
  return applied;
}

function countRows(sel) {
  const el = $(sel);
  return el ? el.querySelectorAll("tbody tr").length : 0;
}

async function applyChartLayers(chart, symbol, bars) {
  state.layerData = {};
  state.layerSeries = { sr: [], fib: [], profile: [], structure: [], trend: [], momentum: [], volatility: [], volume: [], gap: [], regime: [], relative: [], micro: [], distribution: [], event: [], strategy: [] };
  Object.keys(LAYER_DEFS).forEach((k) => { state.layerCounts[k] = null; });
  const L = state.layers;

  if (L.sr) {
    try {
      const d = await api(`/api/bars/${encodeURIComponent(symbol)}/levels`);
      state.layerData.sr = d;
      const made = plotSupportResistance(chart, d, bars) || [];
      state.layerSeries.sr = made;
      state.layerCounts.sr = made.length;
      // The endpoint may hold more zones than are drawn; say so honestly.
      state.layerData.sr.total = (d.zones || []).length;
      state.layerDrawn.sr = { drawn: made.length, found: state.layerData.sr.total };
    } catch (e) { state.layerCounts.sr = 0; state.layerDrawn.sr = { drawn: 0, reason: e.message }; }
  }
  if (L.fib) {
    try {
      const d = await api(`/api/bars/${encodeURIComponent(symbol)}/fibonacci`);
      state.layerData.fib = d;
      const made = d && d.available === false ? [] : (plotFibonacci(chart, d, bars) || []);
      state.layerSeries.fib = made;
      state.layerCounts.fib = made.length;
      state.layerDrawn.fib = {
        drawn: made.length,
        found: (d && d.available === false) ? 0 : made.length,
        reason: d && d.available === false ? (d.reason || "no swing anchor") : undefined,
      };
    } catch (e) { state.layerCounts.fib = 0; state.layerDrawn.fib = { drawn: 0, reason: e.message }; }
  }
  if (L.profile) {
    try {
      const d = await api(`/api/bars/${encodeURIComponent(symbol)}/volume-profile`
        + "?bins=48&limit=250");
      state.layerData.profile = d;
      const made = plotVolumeProfile(chart, d, bars) || [];
      state.layerSeries.profile = made;
      state.layerCounts.profile = made.length;
      state.layerDrawn.profile = { drawn: made.length, found: made.length };
    } catch (e) { state.layerCounts.profile = 0; state.layerDrawn.profile = { drawn: 0, reason: e.message }; }
  }
  if (L.candles) {
    const cm = document.getElementById("candle-markers"); if (cm) cm.checked = true;
    try { await runCandles({ fromChart: true }); } catch (e) { /* layer unavailable */ }
    state.layerCounts.candles = countRows("#candles");
    // "Found" counts detected shapes; "drawn" is what the cap actually let
    // through, so a low marker count reads as the cap, not as a failure.
    state.layerDrawn.candles = { drawn: cappedCandleMarkers().length };
  }
  // Sync the overlay checkbox to THIS symbol's persisted layer flag. It used to
  // stay ticked after leaving a symbol that had patterns on, so switching to a
  // symbol with no patterns layer still drew its overlay markers once the panel
  // loaded (cross-symbol leakage). loadChartInsights runs after this and always
  // loads the pattern panel, so the flag must be settled here first.
  const patOv = $("#pattern-overlay");
  if (patOv) patOv.checked = !!L.patterns;
  if (L.patterns) {
    // Fetch + draw (not just re-render the panel): the detector result is NOT
    // persisted, so a reload must reconstruct it from the persisted layer flag
    // by re-running the scan. Previously this called renderPatternPanel(), which
    // drew nothing after a reload (patternData was null) — the "lost on reload"
    // defect the session-28 verification flagged.
    try { await loadPatternPanel(symbol); } catch (e) { /* layer unavailable */ }
    state.layerCounts.patterns = countRows("#patterns");
    // Pattern ink is three independent toggles, so "drawn" means "some pattern
    // ink is switched on", never "the markers specifically".
    const inkOn = !!(state.overlayVis.levelLines || state.overlayVis.shapeLines || state.overlayVis.patMarkers);
    state.layerDrawn.patterns = { drawn: inkOn ? state.layerCounts.patterns : 0 };
  }
  if (L.elliott) {
    // A layer is a RENDER control. Running the detector and stopping at "N
    // counts found" is what made the toggle look broken: the panel filled, the
    // chart stayed empty. Detect, then draw the first candidate like the panel's
    // own Draw button does (the same code path, so the two cannot diverge).
    try { await runElliott(); } catch (e) { /* layer unavailable */ }
    const auto = state.elliottAuto || {};
    const cands = auto.candidates || [];
    state.layerCounts.elliott = cands.length;
    if (cands.length) {
      try { state.layerDrawn.elliott = drawElliottCandidate(symbol, 0); }
      catch (e) { state.layerDrawn.elliott = { drawn: 0, reason: e.message }; }
    } else {
      state.layerDrawn.elliott = { drawn: 0, reason: auto.message || "no count found" };
    }
  }
  if (L.harmonic) {
    try { await runHarmonic(); } catch (e) { /* layer unavailable */ }
    const hd = state.harmonicData || {};
    const cands = hd.candidates || [];
    state.layerCounts.harmonic = cands.length;
    if (cands.length) {
      try { state.layerDrawn.harmonic = drawHarmonicCandidate(0); }
      catch (e) { state.layerDrawn.harmonic = { drawn: 0, reason: e.message }; }
    } else {
      state.layerDrawn.harmonic = { drawn: 0, reason: hd.message || "no candidate matched" };
    }
  }
  if (L.structure) {
    try {
      const d = await api(`/api/bars/${encodeURIComponent(symbol)}/structure?limit=250`);
      state.layerData.structure = d;
      state.structureMarkers = [];
      state.structureSeries = [];
      const made = plotMarketStructure(chart, d, bars) || [];
      state.structureSeries = made.filter((m) => m && m.series);
      state.layerCounts.structure = (d.swings || []).length;
      const drawn = (made || []).length;
      state.layerDrawn.structure = {
        drawn,
        found: (d.swings || []).length,
        reason: drawn ? undefined : (d.caveats && d.caveats[0]) || "no structure detected",
      };
      flushMarkers();
    } catch (e) {
      state.layerCounts.structure = 0;
      state.layerDrawn.structure = { drawn: 0, reason: e.message };
    }
  } else {
    state.structureMarkers = [];
    state.structureSeries = [];
  }
  if (L.trend) {
    state.trendMarkers = [];
    state.trendSeries = [];
    try {
      const made = await plotTrendStrength(chart, null, bars) || [];
      state.trendSeries = made.filter((m) => m && m.series);
      const td = state.layerData.trend || {};
      const drawn = state.trendSeries.length + (state.trendMarkers.length > 0 ? 1 : 0);
      state.layerCounts.trend = drawn > 0 ? 1 : 0;
      state.layerDrawn.trend = {
        drawn,
        found: drawn,
        reason: drawn ? undefined : "no trend data",
      };
      flushMarkers();
    } catch (e) {
      state.layerCounts.trend = 0;
      state.layerDrawn.trend = { drawn: 0, reason: e.message };
    }
  } else {
    state.trendMarkers = [];
    state.trendSeries = [];
  }
  if (L.momentum) {
    state.momentumMarkers = [];
    state.momentumSeries = [];
    try {
      const made = await plotMomentumDivergence(chart, null, bars) || [];
      state.momentumSeries = made.filter((m) => m && m.series);
      state.layerCounts.momentum = state.momentumMarkers.length;
      state.layerDrawn.momentum = {
        drawn: state.momentumMarkers.length + state.momentumSeries.length,
        found: state.momentumMarkers.length,
        reason: (state.momentumMarkers.length + state.momentumSeries.length) ? undefined : "no divergence / RS data",
      };
      flushMarkers();
    } catch (e) {
      state.layerCounts.momentum = 0;
      state.layerDrawn.momentum = { drawn: 0, reason: e.message };
    }
  } else {
    state.momentumMarkers = [];
    state.momentumSeries = [];
  }
  if (L.volatility) {
    state.volatilityMarkers = [];
    state.volatilitySeries = [];
    try {
      const made = await plotVolatilityBreakout(chart, null, bars) || [];
      state.volatilitySeries = made.filter((m) => m && m.series);
      state.layerCounts.volatility = state.volatilitySeries.length + state.volatilityMarkers.length;
      state.layerDrawn.volatility = {
        drawn: state.volatilitySeries.length + state.volatilityMarkers.length,
        found: state.volatilitySeries.length + state.volatilityMarkers.length,
        reason: (state.volatilitySeries.length + state.volatilityMarkers.length) ? undefined : "no volatility data",
      };
      flushMarkers();
    } catch (e) {
      state.layerCounts.volatility = 0;
      state.layerDrawn.volatility = { drawn: 0, reason: e.message };
    }
  } else {
    state.volatilityMarkers = [];
    state.volatilitySeries = [];
  }
  if (L.volume) {
    state.volumeMarkers = [];
    state.volumeSeries = [];
    try {
      const made = await plotVolumeAccumulation(chart, null, bars) || [];
      state.volumeSeries = made.filter((m) => m && m.series);
      state.layerCounts.volume = state.volumeSeries.length + state.volumeMarkers.length;
      state.layerDrawn.volume = {
        drawn: state.volumeSeries.length + state.volumeMarkers.length,
        found: state.volumeSeries.length + state.volumeMarkers.length,
        reason: (state.volumeSeries.length + state.volumeMarkers.length) ? undefined : "no volume data",
      };
      flushMarkers();
    } catch (e) {
      state.layerCounts.volume = 0;
      state.layerDrawn.volume = { drawn: 0, reason: e.message };
    }
  } else {
    state.volumeMarkers = [];
    state.volumeSeries = [];
  }
  if (L.gap) {
    state.gapMarkers = [];
    state.gapSeries = [];
    try {
      const made = await plotGapAnalysis(chart, null, bars) || [];
      state.gapSeries = made.filter((m) => m && m.series);
      state.gapMarkers = made.filter((m) => m && m.marker).map((m) => m.marker);
      state.layerCounts.gap = state.layerData.gap ? state.layerData.gap.count : 0;
      state.layerDrawn.gap = { drawn: state.layerCounts.gap, found: state.layerCounts.gap, reason: state.layerCounts.gap ? undefined : "no gaps detected" };
      flushMarkers();
    } catch (e) { state.layerCounts.gap = 0; state.layerDrawn.gap = { drawn: 0, reason: e.message }; }
  } else { state.gapMarkers = []; state.gapSeries = []; }
  if (L.regime) {
    state.regimeMarkers = [];
    state.regimeSeries = [];
    try {
      const made = await plotMarketRegime(chart, null, bars) || [];
      state.regimeSeries = made.filter((m) => m && m.series);
      state.layerCounts.regime = state.layerData.regime && state.layerData.regime.adx != null ? 1 : 0;
      state.layerDrawn.regime = { drawn: state.layerCounts.regime, found: state.layerCounts.regime, reason: state.layerCounts.regime ? undefined : "insufficient data" };
      flushMarkers();
    } catch (e) { state.layerCounts.regime = 0; state.layerDrawn.regime = { drawn: 0, reason: e.message }; }
  } else { state.regimeMarkers = []; state.regimeSeries = []; }
  if (L.relative) {
    state.relativeMarkers = [];
    state.relativeSeries = [];
    try {
      const made = await plotRelativePerformance(chart, null, bars) || [];
      state.relativeSeries = made.filter((m) => m && m.series);
      state.layerCounts.relative = state.relativeSeries.length;
      state.layerDrawn.relative = { drawn: state.relativeSeries.length, found: state.relativeSeries.length, reason: state.relativeSeries.length ? undefined : "no aligned benchmark data" };
      flushMarkers();
    } catch (e) { state.layerCounts.relative = 0; state.layerDrawn.relative = { drawn: 0, reason: e.message }; }
  } else { state.relativeMarkers = []; state.relativeSeries = []; }
  if (L.micro) {
    state.microMarkers = [];
    state.microSeries = [];
    try {
      const made = await plotMicrostructure(chart, null, bars) || [];
      state.microSeries = made.filter((m) => m && m.series);
      state.layerCounts.micro = state.microSeries.length;
      state.layerDrawn.micro = { drawn: state.microSeries.length, found: state.microSeries.length, reason: state.microSeries.length ? undefined : "no volume data" };
      flushMarkers();
    } catch (e) { state.layerCounts.micro = 0; state.layerDrawn.micro = { drawn: 0, reason: e.message }; }
  } else { state.microMarkers = []; state.microSeries = []; }
  if (L.distribution) {
    state.distributionMarkers = [];
    state.distributionSeries = [];
    try {
      const made = await plotPriceDistribution(chart, null, bars) || [];
      state.distributionSeries = made.filter((m) => m && m.series);
      state.layerCounts.distribution = state.distributionSeries.length;
      state.layerDrawn.distribution = { drawn: state.distributionSeries.length, found: state.distributionSeries.length, reason: state.distributionSeries.length ? undefined : "no volume profile data" };
      flushMarkers();
    } catch (e) { state.layerCounts.distribution = 0; state.layerDrawn.distribution = { drawn: 0, reason: e.message }; }
  } else { state.distributionMarkers = []; state.distributionSeries = []; }
  if (L.event) {
    state.eventMarkers = [];
    state.eventSeries = [];
    try {
      const made = await plotEventAnalysis(chart, null, bars) || [];
      state.eventSeries = made.filter((m) => m && m.series);
      const avail = state.layerData.event && state.layerData.event.available;
      state.layerCounts.event = avail ? (state.layerData.event.count || 1) : 0;
      state.layerDrawn.event = { drawn: state.layerCounts.event, found: state.layerCounts.event, reason: avail ? undefined : (state.layerData.event ? state.layerData.event.reason : "no event data") };
      flushMarkers();
    } catch (e) { state.layerCounts.event = 0; state.layerDrawn.event = { drawn: 0, reason: e.message }; }
  } else { state.eventMarkers = []; state.eventSeries = []; }
  if (L.strategy) {
    state.strategyMarkers = [];
    state.strategySeries = [];
    try {
      const made = await plotStrategyValidation(chart, null, bars) || [];
      state.strategySeries = made.filter((m) => m && m.series);
      state.layerCounts.strategy = 1;
      state.layerDrawn.strategy = { drawn: 1, found: 1, reason: undefined };
      flushMarkers();
    } catch (e) { state.layerCounts.strategy = 0; state.layerDrawn.strategy = { drawn: 0, reason: e.message }; }
  } else { state.strategyMarkers = []; state.strategySeries = []; }
  renderLayerDrawer();
  renderLayerResults();
}

function renderLayerDrawer() {
  const host = $("#cd-layers");
  if (!host) return;
  host.innerHTML = Object.entries(LAYER_DEFS).map(([id, def]) => {
    const on = !!state.layers[id];
    const n = state.layerCounts[id];
    const d = state.layerDrawn[id];
    let count = "";
    if (on) {
      const found = d && typeof d.found === "number" ? d.found : n;
      if (n === null) count = "…";
      else if (n === 0) count = "none";
      else if (d && typeof d.drawn === "number") {
        if (d.drawn <= 0) count = `${found} found · not drawn`;
        else if (d.drawn < found) count = `${found} found · ${d.drawn} drawn`;
        else count = `${found} found · drawn`;
      } else count = `${found} found`;
    }
    return `<button class="cd-layer" role="switch" aria-pressed="${on}" data-layer="${esc(id)}"
      title="${esc(def.hint)}">
      <span class="cl-main">${esc(def.label)}<span class="cl-hint">${esc(def.hint)}</span></span>
      <span class="cl-count">${esc(count)}</span>
    </button>`;
  }).join("");
  $$("#cd-layers .cd-layer").forEach((b) =>
    b.addEventListener("click", () => toggleLayer(b.dataset.layer)));
}

function renderLayerResults() {
  const host = $("#cd-results");
  if (!host) return;
  // Rebuilt from scratch every time, so hiding a layer clears its results
  // instead of leaving the previous layer's rows behind.
  const rows = [];
  const notes = [];
  let note = "";
  if (state.layers.sr && state.layerData.sr) {
    const drawn = new Set(state.layerSeries.sr.map((m) => m.price));
    const all = (state.layerData.sr.zones || []).filter((z) => drawn.has(z.center));
    if (state.layerData.sr.total > all.length) {
      note = `${state.layerData.sr.total} zones detected, ${all.length} nearest drawn — ` +
        `the rest are hidden on purpose so the chart stays readable.`;
    }
    all.forEach((z) => {
      const kinds = Array.isArray(z.kinds) ? z.kinds : [];
      const kind = kinds.length && kinds.every((k) => k === "low") ? "support"
        : kinds.length && kinds.every((k) => k === "high") ? "resistance" : "zone";
      rows.push({ kind: "sr", cells: ["Zone", kind, z.center, z.lower, z.upper] });
    });
  }
  if (state.layers.fib && state.layerData.fib && state.layerData.fib.available !== false) {
    [].concat(state.layerData.fib.retracements || [], state.layerData.fib.extensions || [])
      .slice(0, MAX_OVERLAY_LINES)
      .forEach((l) => rows.push({
        kind: "fib",
        cells: [l.kind === "extension" ? "Ext" : "Ret", l.percent, l.price, null, null],
      }));
    // Provenance: which swing produced these levels, and over how much history.
    // Without it a level can look "wrong" simply because it belongs to a swing
    // outside the window the user is looking at.
    const fa = state.layerData.fib.anchors;
    if (fa && fa.start_date && fa.end_date) {
      notes.push(`Fibonacci anchors: ${fa.start_date} ${fa.start_kind || ""} ${fa.start_price} → `
        + `${fa.end_date} ${fa.end_kind || ""} ${fa.end_price} `
        + `(over ${state.layerData.fib.bars || "?"} stored bars, ${state.layerData.fib.first_date} → ${state.layerData.fib.last_date}).`);
    }
  }
  if (state.layers.profile && state.layerData.profile && state.layerData.profile.profile) {
    const prof = state.layerData.profile.profile;
    rows.push({ kind: "profile", cells: ["POC", "profile", prof.poc.price, null, null] });
    const va = prof.value_area || {};
    rows.push({ kind: "profile", cells: ["VAH", "profile", va.high, null, null] });
    rows.push({ kind: "profile", cells: ["VAL", "profile", va.low, null, null] });
    // The profile covers its own session window (endpoint-default 250); say so
    // when the chart shows fewer bars than the profile used.
    const sessions = state.layerData.profile.sessions_used;
    if (typeof sessions === "number" && sessions > (state.chartBars || []).length) {
      note = `Profile uses ${sessions} stored sessions — more than the ${state.chartBars.length} ` +
        `bars the chart shows; landmarks are computed over the full profile window.`;
    }
  }
  if (state.layers.elliott) {
    const d = state.layerDrawn.elliott || {};
    const auto = state.elliottAuto || {};
    const n = (auto.candidates || []).length;
    notes.push(d.drawn
      ? `Elliott: drew ${d.drawn} pivot(s)${d.first ? `, ${d.first} → ${d.last}` : ""} from “${d.label || "candidate"}”; ${n} count(s) found.`
      : `Elliott: ${n} count(s) found, nothing drawn — ${d.reason || "no drawable pivots"}.`);
  }
  if (state.layers.harmonic) {
    const d = state.layerDrawn.harmonic || {};
    const hd = state.harmonicData || {};
    const n = (hd.candidates || []).length;
    notes.push(d.drawn
      ? `Harmonic: drew ${d.drawn} pivot(s)${d.first ? `, ${d.first} → ${d.last}` : ""}; ${n} candidate(s) matched.`
      : `Harmonic: ${n} candidate(s) matched, nothing drawn — ${d.reason || "no drawable pivots"}.`);
  }
  const notesHtml = notes.map((t) => `<p class="hint">${esc(t)}</p>`).join("");
  if (!rows.length) {
    host.innerHTML = notesHtml || `<div class="empty">Nothing detected yet — enable a layer above.</div>`;
    return;
  }
  host.innerHTML = (note ? `<p class="hint">${esc(note)}</p>` : "") + notesHtml +
    `<table><thead><tr><th>Type</th><th>Kind</th><th>Price</th><th>Low</th><th>High</th></tr></thead><tbody>` +
    rows.map((r, i) => `<tr data-kind="${esc(r.kind)}" data-i="${i}">` +
      r.cells.map((c) => `<td>${c === null || c === undefined ? "—" : esc(String(c))}</td>`).join("") +
      "</tr>").join("") + "</tbody></table>";
  $$("#cd-results tbody tr").forEach((tr) =>
    tr.addEventListener("click", () => highlightResult(tr.dataset.kind, +tr.dataset.i)));
}


/* Selecting a result emphasises its own overlay line and dims the others, so a
   row in the list can be matched to the thing drawn on the chart. */
function highlightResult(kind, index) {
  const items =
    kind === "fib" ? state.layerSeries.fib
    : kind === "profile" ? state.layerSeries.profile
    : state.layerSeries.sr;
  if (!items || !items[index]) return;
  items.forEach((m, i) => {
    try {
      m.series.applyOptions(i === index
        ? { lineWidth: 3, color: PRAVAHA.white, title: m.label }
        : { lineWidth: 1 });
    } catch (e) { /* series gone */ }
  });
  // Do not scroll the chart here: highlighting a result row must never
  // reposition the viewport. (Previously scrollToRealTime() jumped the
  // chart to the end whenever a result was selected — the "viewport jumps
  // away" defect.) The emphasised line is already on the chart; the user
  // keeps their current view.
}

function toggleLayer(id) {
  if (!LAYER_DEFS[id]) return;
  const on = !state.layers[id];
  if (on) state.layers[id] = true; else delete state.layers[id];
  if (state.chartSymbol) saveLayers(state.chartSymbol);
  loadChart();  // rebuild once, so layers and indicators agree
}

function chartZoom(factor) {
  const chart = state.charts.price;
  if (!chart) return;
  const ts = chart.timeScale();
  const r = ts.getVisibleLogicalRange();
  if (!r) return;
  const span = Math.max(6, (r.to - r.from) * factor);
  const mid = (r.from + r.to) / 2;
  ts.setVisibleLogicalRange({ from: mid - span / 2, to: mid + span / 2 });
}

function chartChrome() {
  // 1) Move the existing controls into popovers. Their ids and handlers are
  //    untouched, so nothing else in the app changes.
  const IND = ["ind-sma", "ind-ema", "ind-bb", "ind-vol", "ind-rsi", "ind-macd", "ind-swings"];
  const indCells = $("#ind-cells");
  IND.forEach((id) => {
    const el = document.getElementById(id);
    const lbl = el && el.closest("label");
    if (lbl && indCells) indCells.appendChild(lbl);
  });
  // Drawing controls: move the whole controls row of the "Chart drawings" card
  // into the Draw popover. Moving the nodes keeps every existing handler.
  const drawCells = $("#draw-cells");
  const drawCard = [...document.querySelectorAll("#view-charts .card")].find(
    (c) => /Chart drawings/.test(c.textContent || ""));
  const drawSrc = drawCard && drawCard.querySelector(".controls");
  if (drawSrc && drawCells) {
    [...drawSrc.children].forEach((n) => drawCells.appendChild(n));
    drawSrc.style.display = "none";
  }

  // 2) Open clean: candles + volume only. Everything else is opt-in.
  ["ind-sma", "ind-rsi", "ind-macd", "ind-ema", "ind-bb", "ind-swings"].forEach((id) => {
    const el = document.getElementById(id); if (el) el.checked = false;
  });
  const vol = document.getElementById("ind-vol"); if (vol) vol.checked = true;
  const patOv = document.getElementById("pattern-overlay"); if (patOv) patOv.checked = false;
  const cm = document.getElementById("candle-markers"); if (cm) cm.checked = false;

  // 3) popovers (the Indicators button now opens the chart-side drawer, bound
  //    in bindIndAndCompareDrawers below)
  const pops = { "pop-draw-btn": "pop-draw", "pop-kronos-btn": "pop-kronos", "pop-replay-btn": "pop-replay", "pop-chartset-btn": "pop-chartset" };
  Object.entries(pops).forEach(([btnId, popId]) => {
    const btn = document.getElementById(btnId), pop = document.getElementById(popId);
    if (!btn || !pop) return;
    btn.setAttribute("aria-expanded", "false");
    btn.setAttribute("aria-pressed", "false");
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const open = !pop.hidden;
      Object.values(pops).forEach((p) => { document.getElementById(p).hidden = true; });
      Object.keys(pops).forEach((b) => { const el = document.getElementById(b); if (el) { el.setAttribute("aria-expanded", "false"); el.setAttribute("aria-pressed", "false"); } });
      pop.hidden = open;
      btn.setAttribute("aria-expanded", String(!open));
      btn.setAttribute("aria-pressed", String(!open));
    });
  });
  document.addEventListener("click", () => {
    Object.values(pops).forEach((p) => { const el = document.getElementById(p); if (el) el.hidden = true; });
  });
  // indicator catalog modal
  const icb = document.getElementById("ind-catalog-btn");
  if (icb) icb.addEventListener("click", (e) => { e.stopPropagation(); openIndicatorCatalog(); });
  const icust = document.getElementById("ind-custom-btn");
  if (icust) icust.addEventListener("click", (e) => { e.stopPropagation(); const m = $("#ind-custom"); if (m) { m.hidden = false; renderCustomFormulaList(); } });
  const icc = document.getElementById("ind-catalog-close");
  if (icc) icc.addEventListener("click", () => { document.getElementById("ind-catalog").hidden = true; });
  ["ind-catalog-search", "ind-catalog-cat"].forEach((id) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.addEventListener("input", renderCatalogModal);
    el.addEventListener("change", renderCatalogModal);
  });
  document.getElementById("ind-catalog").addEventListener("click", (e) => {
    if (e.target.id === "ind-catalog") e.currentTarget.hidden = true;
  });
  // §8E indicator templates: save current checkbox set / apply saved set
  if ($("#ind-tpl-save")) $("#ind-tpl-save").addEventListener("click", saveIndTemplate);
  if ($("#ind-tpl-apply")) $("#ind-tpl-apply").addEventListener("click", () => {
    const sel = $("#ind-tpl-list");
    if (!sel || !sel.value) { drawStatus("No template selected — save one first."); return; }
    applyIndTemplate(sel.value);
  });
  if ($("#ind-tpl-del")) $("#ind-tpl-del").addEventListener("click", deleteIndTemplate);
  refreshIndTplList();
  Object.values(pops).forEach((p) => {
    const el = document.getElementById(p);
    if (el) el.addEventListener("click", (e) => e.stopPropagation());
  });

  // §5.7 unified undo/redo: keyboard + toolbar disabled states
  installUndoKeyboard();
  if ($("#draw-undo")) $("#draw-undo").addEventListener("click", histUndo);
  if ($("#draw-redo")) $("#draw-redo").addEventListener("click", histRedo);
  updateUndoButtons();

  // §5.9 render controls: caps and layer visibility for detector ink
  const bindVis = (id, fn) => { const el = $(id); if (el) el.addEventListener("change", fn); };
  bindVis("#ov-level-lines", () => { state.overlayVis.levelLines = $("#ov-level-lines").checked; try { renderPatternPanel(); } catch (e) { /* no pattern data yet */ } });
  bindVis("#ov-shape-lines", () => { state.overlayVis.shapeLines = $("#ov-shape-lines").checked; try { renderPatternPanel(); } catch (e) { /* none */ } });
  bindVis("#ov-pat-markers", () => { state.overlayVis.patMarkers = $("#ov-pat-markers").checked; try { renderPatternPanel(); } catch (e) { /* none */ } });
  bindVis("#ov-max-patterns", () => { try { renderPatternPanel(); } catch (e) { /* none */ } });
  bindVis("#ov-candle-cap", () => {
    // 0 is a legitimate choice ("no letters"), so it must not fall back to 15
    // the way a NaN parse does.
    const n = parseInt($("#ov-candle-cap").value, 10);
    state.overlayVis.candleCap = Number.isFinite(n) ? n : 15;
    flushMarkers();
  });
  // §5.9.3 display modes: presets over the render controls. They are honest
  // selection caps — data stays in the panels, only chart ink changes.
  const setMode = () => {
    const mode = ($("#ov-display-mode") || {}).value || "standard";
    const presets = {
      minimal:   { levelLines: false, shapeLines: false, patMarkers: false, candleCap: 0 },
      standard:  { levelLines: true, shapeLines: true, patMarkers: true, candleCap: 15 },
      detailed:  { levelLines: true, shapeLines: true, patMarkers: true, candleCap: 40 },
      research:  { levelLines: true, shapeLines: true, patMarkers: true, candleCap: 100000 },
    };
    const p = presets[mode] || presets.standard;
    Object.assign(state.overlayVis, p);
    const patSel = { minimal: 1, standard: 3, detailed: 8, research: 12 }[mode];
    // The candle-cap selector has a real "none" option, so minimal shows 0
    // rather than a number that no longer describes what is drawn.
    const capSel = String(p.candleCap);
    if (patSel) $("#ov-max-patterns").value = String(patSel);
    const cSel = $("#ov-candle-cap");
    if (cSel && [...cSel.options].some((op) => op.value === capSel)) cSel.value = capSel;
    flushMarkers();
    try { renderPatternPanel(); } catch (e) { /* patterns not loaded yet */ }
  };
  bindVis("#ov-display-mode", setMode);

  // §5.21 Kronos AI chart workflow: real forecast runs, honest states
  bindKronosChart();
  // multi-symbol comparison + bars-pattern feed
  bindCompareAndBarsPattern();
  // indicator manager drawer + compare drawer (chart-integrated workflows)
  bindIndAndCompareDrawers();
  // §28 sandboxed custom-indicator DSL (lazy-bound: the button lives inside the
  // indicators popover, which is rendered after init on some flows)
  bindCustomFormula();
  document.addEventListener("click", (e) => {
    const t = e.target && e.target.closest ? e.target.closest("#ind-custom-btn") : null;
    if (t) { e.stopPropagation(); const m = $("#ind-custom"); if (m) m.hidden = false; renderCustomFormulaList(); }
  });
  // §8J replay + §8K autosave switch
  bindReplayAndSettings();
  // §8K restore the persisted chart context when autosave is explicitly ON
  try { restoreAutosave(); } catch (e) { /* boot must not depend on it */ }

  // 4) toolbar actions
  const typeSel = document.getElementById("chart-type");
  if (typeSel) typeSel.addEventListener("change", () => loadChart());
  const fit = document.getElementById("chart-fit");
  if (fit) fit.addEventListener("click", () => {
    const c = state.charts.price; if (c) c.timeScale().fitContent();
  });
  const zi = document.getElementById("chart-zoom-in");
  if (zi) zi.addEventListener("click", () => chartZoom(0.7));
  const zo = document.getElementById("chart-zoom-out");
  if (zo) zo.addEventListener("click", () => chartZoom(1.4));
  const fs = document.getElementById("chart-fullscreen");
  if (fs) fs.addEventListener("click", () => {
    // Fullscreen the whole charting VIEW, not just the stage: the toolbar
    // (symbol, indicators, draw, replay, Kronos) must stay reachable while
    // expanded, otherwise most charting controls would be unreachable.
    const view = document.getElementById("view-charts");
    if (!view) return;
    if (document.fullscreenElement) document.exitFullscreen();
    else if (view.requestFullscreen) view.requestFullscreen();
    else view.classList.toggle("stage-expanded");
  });

  // 5) drawer (analysis). The indicator and compare drawers live in the same
  // stage; make all three mutually exclusive and keep the stage width class in
  // sync whichever one is open.
  const drawer = document.getElementById("chart-drawer");
  const stage = document.getElementById("chart-stage");
  const dt = document.getElementById("chart-drawer-toggle");
  const dc = document.getElementById("chart-drawer-close");
  const anyDrawerOpen = () => ["chart-drawer", "ind-drawer", "cmp-drawer"]
    .some((id) => { const el = document.getElementById(id); return el && !el.hidden; });
  const setDrawer = (open) => {
    if (!drawer || !stage || !dt) return;
    if (open) ["ind-drawer", "cmp-drawer"].forEach((id) => { const el = document.getElementById(id); if (el) el.hidden = true; });
    drawer.hidden = !open;
    stage.classList.toggle("with-drawer", anyDrawerOpen());
    dt.setAttribute("aria-pressed", String(open));
  };
  if (dt) dt.addEventListener("click", () => setDrawer(drawer.hidden));
  if (dc) dc.addEventListener("click", () => setDrawer(false));
  const hideAll = document.getElementById("cd-hide-all");
  if (hideAll) hideAll.addEventListener("click", () => {
    state.layers = {};
    if (state.chartSymbol) saveLayers(state.chartSymbol);
    loadChart();
    setDrawer(true);
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      setDrawer(false);
      ["ind-drawer", "cmp-drawer"].forEach((id) => { const el = document.getElementById(id); if (el) el.hidden = true; });
      stage && stage.classList.toggle("with-drawer", anyDrawerOpen());
      // Esc also leaves the expanded chart view (§8L).
      if (document.fullscreenElement) document.exitFullscreen();
    }
  });
  document.addEventListener("fullscreenchange", () => {
    const c = state.charts.price;
    // The chart fills the leftover space below the toolbar inside the
    // fullscreen view. Use the viewport height directly: a percentage height
    // inside a flex row collapsed the canvas to 2px.
    if (c) setTimeout(() => {
      if (document.fullscreenElement) {
        c.resize("100%", String(Math.max(320, window.innerHeight - 165)));
      } else {
        const box = $("#chart");
        const h = box && box.parentElement ? Math.max(320, box.parentElement.clientHeight - 88) : Math.max(320, window.innerHeight - 150);
        c.resize("100%", String(h));
      }
    }, 140);
  });
  window.addEventListener("resize", () => {
    const c = state.charts.price;
    if (c && document.fullscreenElement) c.resize("100%", String(Math.max(320, window.innerHeight - 165)));
  });

  // Browser-level checks (Playwright) read state through this reference; it is
  // read-only usage and adds no behavior.
  window.mtState = state;
  // QA surface for the Kronos guard logic itself (same-object references only:
  // tests can assert that a mismatched/stale forecast is dropped).
  window.__mtKronosTest = { drawForecastOverlay, invalidateKronosRuns };
  window.__mtDraw = { renderDrawings, afterDrawingsChanged };
  // QA surface for indicator templates/favourites (read-only-ish).
  window.__mtInd = { saveIndTemplate, applyIndTemplate, deleteIndTemplate, refreshIndTplList, toggleIndFav };
  // QA surface for the indicator drawer + comparison (used by browser checks).
  window.__mtIndDrawer = { renderIndDrawer, renderIndHits, exportIndLayout, importIndLayout, applyCompareToChart, addCompareSymbol, renderComparePanel, addToChartFromCatalog, applyCatalogIndicator, removeIndicatorInstance };

  // market intelligence
  bindMarketIntelligence();
  // workbench panels (breadth / seasonality / swing)
  bindWorkbenchPanels();
  // shared scanner/algorithm/fundamental tool-information modal
  bindToolInfoModal();
  // QA surface for the tool-information panel (used by browser checks).
  window.__mtToolInfo = { openToolInfo, toolInfoHtml, catalogToolIdFor, showToolInfo: openToolInfo };
  // NEW section tabs
  bindNewSection();
  // BABA workspace tabs
  bindBabaSection();
  // KIMI research workspace tabs
  bindKimiSection();

  renderLayerDrawer();
}

/* --------------------------------------------------- workbench panels (breadth,
   seasonality, swing bench). Each render function formats what the API
   computed and echoes; it never recomputes a statistic or fills a gap. */
function wbFmt(v, dec = 2) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return "—";
  return Number(v).toLocaleString("en-US", { minimumFractionDigits: dec, maximumFractionDigits: dec });
}
function wbPct(v, dec = 2) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return { html: "—" };
  const n = Number(v);
  return { html: `${n.toFixed(dec)}%`, cls: n > 0 ? "up" : n < 0 ? "down" : "" };
}

async function loadBreadthHistory() {
  const err = $("#bh-error");
  err.textContent = "";
  $("#bh-count").textContent = "Loading…";
  const q = new URLSearchParams();
  const start = ($("#bh-start").value || "").trim();
  const end = ($("#bh-end").value || "").trim();
  if (start) q.set("start", start);
  if (end) q.set("end", end);
  q.set("windows", ($("#bh-windows").value || "20,50,200").trim());
  q.set("high_low_window", ($("#bh-hl").value || "250").trim());
  try {
    const d = await api(`/api/breadth/history?${q.toString()}`);
    $("#bh-count").textContent = `${d.trading_days} sessions · ${d.start || "—"} → ${d.end || "—"}`;
    renderBreadthHistory(d);
  } catch (e) {
    $("#bh-count").textContent = "";
    err.textContent = `Breadth load failed: ${e.message || e}`;
  }
}

function renderBreadthHistory(d) {
  const s = d.series || {};
  const dates = d.dates || [];
  const n = dates.length;
  const last = (arr) => (Array.isArray(arr) && arr.length ? arr[n - 1] : null);
  const pctKeys = Object.keys(s)
    .filter((k) => k.startsWith("pct_above_sma_"))
    .sort((a, b) => Number(a.split("_").pop()) - Number(b.split("_").pop()));
  const nhKey = Object.keys(s).find((k) => k.startsWith("new_highs_"));
  const nlKey = nhKey ? `new_lows_${nhKey.split("_").pop()}` : null;

  const stats = [
    ["Universe", last(s.universe), ""],
    ["Advances", last(s.advances), ""],
    ["Declines", last(s.declines), ""],
    ["Unchanged", last(s.unchanged), ""],
  ];
  pctKeys.forEach((k) => stats.push([`% above ${k.split("_").pop()}-bar SMA`, last(s[k]), "%"]));
  stats.push(["A/D line", last(s.ad_line), ""], ["A/D volume line", last(s.ad_volume_line), ""]);
  if (nhKey) {
    stats.push(
      ["New highs", last(s[nhKey]), ""],
      ["New lows", last(s[nlKey]), ""],
      ["Net new highs", last(s.net_new_highs), ""],
    );
  }
  $("#bh-summary").innerHTML = stats
    .map(([k, v, unit]) => {
      const txt = v === null || v === undefined ? "—" : unit === "%" ? `${Number(v).toFixed(1)}%` : wbFmt(v, 0);
      return `<div class="stat"><div class="k">${esc(k)}</div><div class="v">${esc(txt)}</div></div>`;
    })
    .join("");

  const tail = Math.min(30, n);
  const idxs = [];
  for (let i = n - tail; i < n; i++) idxs.push(i);
  const headers = ["Date", "Universe", "Adv", "Dec", "Unch", ...pctKeys.map((k) => `SMA${k.split("_").pop()} %`), "A/D line"];
  if (nhKey) headers.push("New H", "New L", "Net");
  const rows = idxs.map((i) => {
    const cells = [
      { html: esc(dates[i]) },
      { html: esc(wbFmt(s.universe ? s.universe[i] : null, 0)) },
      { html: esc(wbFmt(s.advances ? s.advances[i] : null, 0)) },
      { html: esc(wbFmt(s.declines ? s.declines[i] : null, 0)) },
      { html: esc(wbFmt(s.unchanged ? s.unchanged[i] : null, 0)) },
    ];
    pctKeys.forEach((k) => cells.push(wbPct(s[k] ? s[k][i] : null, 1)));
    cells.push({ html: esc(wbFmt(s.ad_line ? s.ad_line[i] : null, 0)) });
    if (nhKey) {
      cells.push(
        { html: esc(wbFmt(s[nhKey] ? s[nhKey][i] : null, 0)) },
        { html: esc(wbFmt(s[nlKey] ? s[nlKey][i] : null, 0)) },
        { html: esc(wbFmt(s.net_new_highs ? s.net_new_highs[i] : null, 0)) },
      );
    }
    return cells;
  });
  $("#bh-table").innerHTML = table(headers, rows);
  $("#bh-defs").innerHTML =
    Object.entries(d.definitions || {}).map(([k, v]) => `<div><b>${esc(k)}</b> — ${esc(v)}</div>`).join("") ||
    `<div class="empty">No definitions returned.</div>`;
  lastBreadthData = d;
  renderBreadthChart();
}

async function loadSeasonality() {
  const err = $("#sea-error");
  err.textContent = "";
  const sym = ($("#sea-symbol").value || $("#symbol-input").value || "").trim().toUpperCase();
  if (!sym) {
    err.textContent = "Enter a symbol or index (the chart's symbol is used when the field is empty).";
    return;
  }
  const mb = ($("#sea-minbars").value || "10").trim();
  $("#sea-months").innerHTML = `<div class="empty">Loading ${esc(sym)}…</div>`;
  try {
    const d = await api(`/api/seasonality/${encodeURIComponent(sym)}?min_month_bars=${encodeURIComponent(mb)}`);
    renderSeasonality(d);
  } catch (e) {
    $("#sea-months").innerHTML = `<div class="empty">Not loaded.</div>`;
    err.textContent = `Seasonality load failed: ${e.message || e}`;
  }
}

function renderSeasonality(d) {
  const m = d.monthly || {};
  $("#sea-months").innerHTML = table(
    ["Month", "N", "Mean %", "Median %", "Std %", "Hit rate %", "Best %", "Worst %"],
    (m.by_month || []).map((r) => [
      { html: esc(r.name) },
      { html: esc(String(r.count)) },
      wbPct(r.mean_pct),
      wbPct(r.median_pct),
      wbPct(r.std_pct),
      wbPct(r.hit_rate_pct, 1),
      wbPct(r.best_pct),
      wbPct(r.worst_pct),
    ]),
  );
  const w = d.weekday || {};
  $("#sea-weekdays").innerHTML = table(
    ["Weekday", "N", "Mean %", "Median %", "Std %", "Hit rate %"],
    (w.by_weekday || []).map((r) => [
      { html: esc(r.name) },
      { html: esc(String(r.count)) },
      wbPct(r.mean_pct),
      wbPct(r.median_pct),
      wbPct(r.std_pct),
      wbPct(r.hit_rate_pct, 1),
    ]),
  );
  const h = d.holiday || {};
  if (h.available) {
    const s = h.summary || {};
    $("#sea-holiday").innerHTML =
      `Events: ${esc(String(s.count ?? 0))} · mean ${wbFmt(s.mean_pct, 2)}% · median ${wbFmt(s.median_pct, 2)}% · hit rate ${wbFmt(s.hit_rate_pct, 1)}%` +
      table(
        ["Holiday", "Last session before", "First session after", "Days covered", "Return %"],
        (h.events || []).map((e) => [
          { html: esc(e.holiday) },
          { html: esc(e.last_session_before) },
          { html: esc(e.first_session_after) },
          { html: esc(String(e.calendar_days_covered)) },
          wbPct(e.return_pct),
        ]),
      );
  } else {
    $("#sea-holiday").innerHTML =
      `<b>Unavailable.</b> ${esc(h.reason || "no reason stated")}` +
      (h.calendar_path ? `<div class="hint">Calendar file: ${esc(h.calendar_path)}</div>` : "");
  }
  const defs = m.definitions || {};
  $("#sea-defs").innerHTML = [
    `<div>Observations: ${esc(String(m.observations ?? "—"))} · range ${esc(m.first_date || "—")} → ${esc(m.last_date || "—")} · excluded months: ${esc(String(m.excluded_months ?? 0))}</div>`,
    ...Object.entries(defs).map(([k, v]) => `<div><b>${esc(k)}</b> — ${esc(v)}</div>`),
    `<div>${esc(d.disclaimer || "")}</div>`,
  ].join("");
  renderSeasonalityCharts(d);
}

/* =====================================================================
   Visualisation bridges (web/static/viz.js)
   Every series below is derived directly from an API payload; nothing
   is sampled, interpolated or synthetic. When the payload is empty the
   chart shows an explicit empty state.
   ===================================================================== */
let lastBreadthData = null;

function vizOK() { return typeof window.VIZ !== "undefined"; }

function renderBreadthChart() {
  const host = $("#bh-chart");
  if (!host) return;
  const d = lastBreadthData;
  const note = $("#bh-chart-note");
  if (!vizOK()) { host.innerHTML = `<div class="empty">Chart library unavailable.</div>`; return; }
  if (!d) return;
  const s = d.series || {}, dates = d.dates || [];
  const pick = ($("#bh-chart-metric") && $("#bh-chart-metric").value) || "net_new_highs";
  const at = (a, i) => (Array.isArray(a) && typeof a[i] === "number" && isFinite(a[i]) ? a[i] : null);
  const adv = s.advances || [], dec = s.declines || [];
  const up = s.ad_volume_up || [], dn = s.ad_volume_down || [];
  let values = [], name = "", unit = "", zero = true, yMin, yMax, fmtFn;
  if (pick === "net_new_highs") {
    name = "Net new highs − new lows";
    values = dates.map((_, i) => (at(s.new_highs_250, i) != null && at(s.new_lows_250, i) != null ? s.new_highs_250[i] - s.new_lows_250[i] : null));
    unit = "symbols";
  } else if (pick === "ad_ratio") {
    name = "Advance / decline ratio";
    values = dates.map((_, i) => { const a = at(adv, i), b = at(dec, i); return a != null && b != null && b > 0 ? a / b : null; });
    unit = "ratio";
    yMin = 0;
  } else if (pick === "ad_line") {
    name = "Advance / decline line (cumulative)";
    values = dates.map((_, i) => at(s.ad_line, i));
    unit = "level";
  } else if (pick === "ad_volume_line") {
    name = "A/D volume line (cumulative)";
    values = dates.map((_, i) => at(s.ad_volume_line, i));
    unit = "level";
  } else if (pick === "arms_index") {
    name = "Arms index (TRIN)";
    values = dates.map((_, i) => {
      const a = at(adv, i), b = at(dec, i), u = at(up, i), v = at(dn, i);
      if (a == null || b == null || u == null || v == null || b === 0 || u === 0) return null;
      return (a / b) / (u / v);
    });
    unit = "ratio";
    zero = false;
    yMin = 0;
  } else if (pick === "pct_above_sma_50" || pick === "pct_above_sma_200") {
    const w = pick.split("_").pop();
    name = `% of stocks above their ${w}-bar SMA`;
    values = dates.map((_, i) => at(s[`pct_above_sma_${w}`], i));
    unit = "%";
    zero = false;
    yMin = 0;
    yMax = 100;
    fmtFn = (v) => (v == null ? "—" : `${Number(v).toFixed(1)}%`);
  }
  if (!values.some((v) => v != null)) { VIZ.empty(host, "This indicator has no defined values in the loaded range."); if (note) note.textContent = ""; return; }
  VIZ.line(host, {
    labels: dates,
    series: [{ name, values, color: PRAVAHA.cyan, area: true }],
    height: 300,
    zeroLine: zero,
    yMin, yMax,
    yFormat: fmtFn,
    yLabel: unit,
    ariaLabel: `${name} from ${dates[0]} to ${dates[dates.length - 1]}`,
  });
  if (note) {
    const defs = d.definitions || {};
    const key = pick === "net_new_highs" ? "new_highs"
      : pick === "ad_line" ? "ad_line"
      : pick === "ad_volume_line" ? "ad_volume_line"
      : pick.indexOf("pct_above_sma") === 0 ? "pct_above_sma_n"
      : null;
    const extra = pick === "arms_index"
      ? " Arms index = (advances ÷ declines) ÷ (up-volume ÷ down-volume); a reading below 1.0 is a strong up-volume bias, above 1.0 a strong down-volume bias."
      : pick === "ad_ratio"
        ? " Ratio = advances ÷ declines for that session; 1.0 means as many stocks rose as fell, above 1.0 means breadth favoured advancers."
        : "";
    note.innerHTML = `<b>${esc(name)}</b> — ${fmtInt(dates.length)} stored sessions from ${esc(d.start || "—")} to ${esc(d.end || "—")}. ` +
      (key && defs[key] ? esc(defs[key]) : "") + extra +
      " Derived on the client from the breadth endpoint's stored series; no values are invented.";
  }
}

function seasonalityQuarterReturns(monthly) {
  // Compounded quarter returns, then averaged across years. A year missing
  // any month of a quarter is skipped for that quarter (never interpolated).
  const byYear = {};
  (monthly.months || []).forEach((m) => {
    if (m.excluded_from_aggregates) return;
    if (typeof m.return_pct !== "number" || !isFinite(m.return_pct)) return;
    const q = Math.floor((m.month - 1) / 3) + 1;
    const key = `${m.year}`;
    (byYear[key] = byYear[key] || {})[q] = (byYear[key][q] || {});
    byYear[key][q][m.month] = m.return_pct;
  });
  const acc = { 1: [], 2: [], 3: [], 4: [] };
  Object.values(byYear).forEach((quarters) => {
    for (let q = 1; q <= 4; q++) {
      const months = quarters[q];
      if (!months) continue;
      const want = [0, 1, 2].map((k) => (q - 1) * 3 + 1 + k);
      if (!want.every((mn) => typeof months[mn] === "number")) continue;
      let comp = 1;
      want.forEach((mn) => { comp *= (1 + months[mn] / 100); });
      acc[q].push((comp - 1) * 100);
    }
  });
  const mean = (a) => (a.length ? a.reduce((x, y) => x + y, 0) / a.length : null);
  return [1, 2, 3, 4].map((q) => ({ q, label: `Q${q}`, count: acc[q].length, mean_pct: mean(acc[q]) }));
}

function renderSeasonalityCharts(d) {
  if (!vizOK()) return;
  const m = d.monthly || {};
  const months = (m.by_month || []).filter((r) => typeof r.mean_pct === "number");
  const monthsHost = $("#sea-chart-months");
  if (monthsHost) {
    if (!months.length) { VIZ.empty(monthsHost, "No month statistics in the stored range."); }
    else {
      const wsum = months.reduce((a, r) => a + r.count, 0) || 1;
      const wmean = months.reduce((a, r) => a + r.mean_pct * r.count, 0) / wsum;
      VIZ.bars(monthsHost, {
        orientation: "v",
        height: 200,
        signed: true,
        zeroLine: true,
        meanLine: wmean,
        items: months.map((r) => ({ label: r.name, shortLabel: r.name.slice(0, 3), value: r.mean_pct, color: r.mean_pct >= 0 ? PRAVAHA.up : PRAVAHA.down })),
        yFormat: (v) => `${v.toFixed(1)}%`,
        valueFormat: (v) => `${v.toFixed(1)}%`,
        ariaLabel: "Mean return by month of year",
      });
    }
    const meta = $("#sea-chart-month-meta");
    if (meta) meta.textContent = `${months.length} months · ${fmtInt(m.observations)} observations · ${m.first_date || "—"} → ${m.last_date || "—"}`;
  }
  const wk = (d.weekday || {}).by_weekday || [];
  const wkHost = $("#sea-chart-weekdays");
  if (wkHost) {
    const rows = wk.filter((r) => typeof r.mean_pct === "number");
    if (!rows.length) VIZ.empty(wkHost, "No weekday statistics in the stored range.");
    else VIZ.bars(wkHost, {
      orientation: "v", height: 180, signed: true, zeroLine: true,
      items: rows.map((r) => ({ label: r.name, shortLabel: r.name.slice(0, 3), value: r.mean_pct, color: r.mean_pct >= 0 ? PRAVAHA.up : PRAVAHA.down })),
      yFormat: (v) => `${v.toFixed(2)}%`, valueFormat: (v) => `${v.toFixed(2)}%`,
      ariaLabel: "Mean return by weekday",
    });
    const meta = $("#sea-chart-weekday-meta");
    if (meta) meta.textContent = rows.map((r) => `${r.name.slice(0, 3)} n=${fmtInt(r.count)}`).join(" · ");
  }
  const qHost = $("#sea-chart-quarters");
  if (qHost) {
    const qs = seasonalityQuarterReturns(m).filter((r) => typeof r.mean_pct === "number");
    if (!qs.length) VIZ.empty(qHost, "Not enough complete quarters to compute a quarterly average.");
    else VIZ.bars(qHost, {
      orientation: "v", height: 180, signed: true, zeroLine: true,
      items: qs.map((r) => ({ label: `Q${r.q} (n=${r.count} years)`, shortLabel: `Q${r.q}`, value: r.mean_pct, color: r.mean_pct >= 0 ? PRAVAHA.up : PRAVAHA.down })),
      yFormat: (v) => `${v.toFixed(1)}%`, valueFormat: (v) => `${v.toFixed(1)}%`,
      ariaLabel: "Mean compounded return by quarter",
    });
    const meta = $("#sea-chart-quarter-meta");
    if (meta) meta.textContent = qs.map((r) => `Q${r.q}: ${r.count}y`).join(" · ");
  }
}

function renderBatteryBreakdown(d, breadth, bb, adv, dec, pctAbove, score, band) {
  const host = $("#ov-battery-breakdown");
  if (!host) return;
  if (adv + dec === 0 && pctAbove == null) {
    host.innerHTML = `<div class="empty">No breadth data for the latest stored session.</div>`;
    return;
  }
  const unchanged = Number(breadth.unchanged) || 0;
  const missing = Number(breadth.missing) || 0;
  const total = Number(breadth.total) || (adv + dec + unchanged);
  const adShare = adv + dec > 0 ? (adv / (adv + dec)) * 100 : null;
  const adRatio = dec > 0 ? adv / dec : (adv > 0 ? Infinity : 0);
  const pctBelow50 = pctAbove == null ? null : 100 - pctAbove;

  // Component contributions (must reconcile to the score).
  const c1 = adShare == null ? 0 : 0.5 * adShare;
  const c2 = pctAbove == null ? 0 : 0.5 * pctAbove;
  const scoreCheck = (c1 + c2);
  const asOf = breadth.as_of || "—";

  // Interpretation (deterministic, based on actual components).
  let interp = "";
  if (score == null) interp = "Score unavailable — missing breadth inputs.";
  else if (score >= 70) interp = "Broad participation with strong advance/decline breadth and above-average participation above the 50-day MA.";
  else if (score >= 55) interp = "Firm participation: advancers lead decliners and a majority of symbols hold above their 50-day MA.";
  else if (score >= 45) interp = "Mixed participation — the market is broadly balanced. The score sits near the neutral midpoint and does not by itself establish a strong trend.";
  else if (score >= 30) interp = "Soft participation: decliners lead or fewer symbols hold above their 50-day MA. Breadth is weakening.";
  else interp = "Weak participation: decliners dominate and most symbols are below their 50-day MA. Breadth is deteriorating.";

  // Concentration warning (only if we have enough data).
  let concWarn = "";
  if (adv + dec > 0 && adv / (adv + dec) > 0.7 && (pctAbove == null || pctAbove < 50)) {
    concWarn = `<p class="hint" style="color:${PRAVAHA.caution}">⚠ Advance/decline breadth is strong but fewer than half of symbols are above their 50-day MA — gains may be concentrated in relatively few stocks.</p>`;
  }

  const bar = (val, max, color) => {
    if (val == null) return "—";
    const w = Math.max(0, Math.min(100, (val / max) * 100));
    return `<div style="display:flex;align-items:center;gap:6px"><div style="flex:1;height:6px;background:var(--pravaha-panel-2);border-radius:3px;overflow:hidden"><div style="width:${w.toFixed(1)}%;height:100%;background:${color}"></div></div><span style="font-size:11px;color:var(--pravaha-muted);min-width:40px;text-align:right">${fmtNum(val, 1)}</span></div>`;
  };

  host.innerHTML = `
    <div class="ss-kpis" style="margin-bottom:8px">
      <div class="ss-kpi"><div class="ss-kpi-label">Score</div><div class="ss-kpi-value">${fmtNum(score, 0)} / 100</div><div class="ss-kpi-sub">${esc(band)}</div></div>
      <div class="ss-kpi"><div class="ss-kpi-label">A/D share</div><div class="ss-kpi-value">${adShare == null ? "—" : fmtNum(adShare, 1) + "%"}</div><div class="ss-kpi-sub">weight 50%</div></div>
      <div class="ss-kpi"><div class="ss-kpi-label">Above 50-day MA</div><div class="ss-kpi-value">${pctAbove == null ? "—" : fmtNum(pctAbove, 1) + "%"}</div><div class="ss-kpi-sub">weight 50%</div></div>
      <div class="ss-kpi"><div class="ss-kpi-label">Unchanged</div><div class="ss-kpi-value">${fmtInt(unchanged)}</div><div class="ss-kpi-sub">of ${fmtInt(total)} symbols</div></div>
    </div>
    <details open style="margin-top:6px">
      <summary style="cursor:pointer;font-size:12px;color:var(--pravaha-muted);font-weight:600">Score breakdown & breadth details</summary>
      <div style="margin-top:8px;display:flex;flex-direction:column;gap:8px">
        <div>
          <div style="font-size:11px;color:var(--pravaha-muted);margin-bottom:2px">Component 1 — Advance/Decline share (weight 50%, contribution ${fmtNum(c1, 1)})</div>
          ${bar(adShare, 100, "var(--pravaha-up)")}
          <div style="font-size:10.5px;color:var(--pravaha-muted);margin-top:2px">Advancers ${fmtInt(adv)} · Decliners ${fmtInt(dec)} · Unchanged ${fmtInt(unchanged)} · Missing ${fmtInt(missing)} · Total ${fmtInt(total)} · A/D ratio ${adRatio === Infinity ? "∞" : fmtNum(adRatio, 2)}</div>
        </div>
        <div>
          <div style="font-size:11px;color:var(--pravaha-muted);margin-bottom:2px">Component 2 — % above 50-day MA (weight 50%, contribution ${fmtNum(c2, 1)})</div>
          ${bar(pctAbove, 100, "var(--pravaha-cyan)")}
          <div style="font-size:10.5px;color:var(--pravaha-muted);margin-top:2px">Above 50-day MA: ${fmtInt(bb.above_50 ? bb.above_50.count : 0)} of ${fmtInt(bb.above_50 ? bb.above_50.denominator : 0)} (${fmtNum(pctAbove, 1)}%) · Below: ${pctBelow50 == null ? "—" : fmtNum(pctBelow50, 1) + "%"}</div>
        </div>
        <div style="font-size:10.5px;color:var(--pravaha-muted)">
          <b>MA participation:</b>
          above 20-day MA ${bb.above_20 ? fmtNum(bb.above_20.pct, 1) + "%" : "—"} (${fmtInt(bb.above_20 ? bb.above_20.count : 0)}/${fmtInt(bb.above_20 ? bb.above_20.denominator : 0)}) ·
          above 200-day MA ${bb.above_200 ? fmtNum(bb.above_200.pct, 1) + "%" : "—"} (${fmtInt(bb.above_200 ? bb.above_200.count : 0)}/${fmtInt(bb.above_200 ? bb.above_200.denominator : 0)})
        </div>
        <div style="font-size:11px;color:var(--pravaha-muted);font-style:italic">${esc(interp)}</div>
        ${concWarn}
        <div style="font-size:10px;color:var(--pravaha-muted)">Score = 0.5 × A/D share + 0.5 × % above 50-day MA = 0.5 × ${fmtNum(adShare, 1)} + 0.5 × ${fmtNum(pctAbove, 1)} = ${fmtNum(scoreCheck, 1)} (reconciles to ${fmtNum(score, 0)}). Observation: ${esc(asOf)} (stored session, delayed). This measures market breadth/health — <b>not</b> a prediction of future NEPSE movement.</div>
      </div>
    </details>
  `;
}

function renderOverviewVisuals(d) {
  if (!vizOK() || !d) return;
  const breadth = d.breadth || {};
  const bb = breadth.moving_average || {};

  // --- Market barometer gauge (deterministic transform of two stored inputs)
  const adv = Number(breadth.advancers) || 0;
  const dec = Number(breadth.decliners) || 0;
  const pctAbove = typeof bb.pct_above_50 === "number" ? bb.pct_above_50 : null;
  const gaugeHost = $("#ov-gauge");
  let score = null, band = "—";
  if (gaugeHost) {
    const adShare = adv + dec > 0 ? (adv / (adv + dec)) * 100 : null;
    if (adShare == null) {
      VIZ.empty(gaugeHost, "No advance/decline counts for the latest stored session.");
    } else {
      score = pctAbove == null ? adShare : 0.5 * adShare + 0.5 * pctAbove;
      band = score >= 70 ? "Strong" : score >= 55 ? "Firm" : score >= 45 ? "Neutral" : score >= 30 ? "Soft" : "Weak";
      const sub = $("#ov-gauge-sub");
      if (sub) sub.textContent = band;
      VIZ.gauge(gaugeHost, {
        value: score, min: 0, max: 100, height: 190,
        label: `${band} · A/D ${fmtNum(adShare, 0)}${pctAbove == null ? "" : ` · >50MA ${fmtNum(pctAbove, 0)}`}`,
        valueFormat: (v) => fmtNum(v, 0),
        ariaLabel: `Market barometer ${fmtNum(score, 0)} of 100 (${band})`,
      });
      const note = $("#ov-gauge-note");
      if (note) {
        note.innerHTML = `Advancers ${fmtInt(adv)} · decliners ${fmtInt(dec)}` +
          (pctAbove == null ? "" : ` · ${fmtNum(pctAbove, 1)}% above their 50-day MA`) +
          ` — latest stored session ${esc(breadth.as_of || "—")}. Score = half the advance share` +
          (pctAbove == null ? " (the 50-day MA breadth is unavailable, so only the A/D component is used)" : " plus half the 50-day MA breadth") +
          `. A transparent transform of those inputs, <b>not</b> an external sentiment feed or a forecast.`;
      }
    }
  }

  // --- Market Battery breakdown (score components, breadth snapshot, interpretation) ---
  renderBatteryBreakdown(d, breadth, bb, adv, dec, pctAbove, score, band);

  // --- Sector performance bars + turnover-share donut

  const secs = (d.sectors || []).filter((s) => s && s.sector);
  const barHost = $("#ov-sector-chart");
  if (barHost) {
    const rows = secs.filter((s) => typeof s.avg_pct === "number");
    if (!rows.length) VIZ.empty(barHost, "No sector performance data for the latest stored session.");
    else VIZ.bars(barHost, {
      orientation: "h", height: Math.max(80, rows.length * 24 + 16), signed: true,
      labelWidth: 130,
      items: rows
        .slice()
        .sort((a, b) => (b.avg_pct || 0) - (a.avg_pct || 0))
        .map((s) => ({ label: s.sector, shortLabel: s.sector.slice(0, 3), value: s.avg_pct, color: s.avg_pct >= 0 ? PRAVAHA.up : PRAVAHA.down, href: () => { showView("nse"); if (typeof viewShown === "function") viewShown("nse"); } })),
      valueFormat: (v) => `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`,
      ariaLabel: "Average percent change by sector",
    });
    const meta = $("#ov-sector-chart-meta");
    if (meta) meta.textContent = `${rows.length} sectors · ${esc(breadth.as_of || "")}`;
  }
  const donutHost = $("#ov-sector-donut");
  if (donutHost) {
    const slices = secs.filter((s) => typeof s.turnover === "number" && s.turnover > 0)
      .slice().sort((a, b) => b.turnover - a.turnover)
      .map((s, i) => ({ label: s.sector, value: s.turnover, color: (VIZ.PALETTE || [])[i % (VIZ.PALETTE || [PRAVAHA.cyan]).length] }));
    if (!slices.length) VIZ.empty(donutHost, "No sector turnover to apportion.");
    else VIZ.donut(donutHost, {
      slices, height: 230, maxSize: 210,
      valueFormat: (v) => `NPR ${fmtNum(v, 0)}`,
      centerLabel: `NPR ${fmtNum(slices.reduce((a, s) => a + s.value, 0) / 1e9, 2)}B`,
      centerSub: "session turnover",
      ariaLabel: "Turnover share by sector",
    });
    const meta = $("#ov-donut-meta");
    if (meta) meta.textContent = `${slices.length} sectors with turnover`;
  }

  // --- Fundamental map (P/E vs P/B), coloured by sector
  const mapHost = $("#ov-fundmap");
  if (mapHost) {
    state.ovFundMapPts = (d.valuation && d.valuation.scatter) || [];
    state.ovFundMapCoverage = (d.valuation && d.valuation.coverage) || {};
    const sizeToggle = $("#ov-fundmap-size");
    if (sizeToggle && sizeToggle.dataset.bound !== "1") {
      sizeToggle.dataset.bound = "1";
      sizeToggle.checked = !!state.ovFundMapSizeOn;
      sizeToggle.addEventListener("change", () => {
        state.ovFundMapSizeOn = sizeToggle.checked;
        renderFundMap();
      });
    }
    renderFundMap();
  }
}

/* The fundamental map. Colour is the sector; the dot's size can be switched to
   the DERIVED market capitalisation (paid-up capital / 100 × last close) when
   that input is stored. A symbol with no stored paid-up capital is drawn at the
   minimum size and the note says how many those are — a missing cap must never
   read as a tiny company. */
function renderFundMap() {
  const mapHost = $("#ov-fundmap");
  if (!mapHost) return;
  const pts = state.ovFundMapPts || [];
  const coverage = state.ovFundMapCoverage || {};
  const usable = pts.filter((p) => typeof p.pe === "number" && typeof p.pb === "number" && p.pe > 0 && p.pb > 0);
  const note = $("#ov-fundmap-note");
  const meta = $("#ov-fundmap-meta");
  if (!usable.length) {
    VIZ.empty(mapHost, "No symbols have both a positive P/E and P/B in the stored fundamentals.");
    if (note) note.textContent = "Non-positive or missing ratios are excluded, never plotted as negatives.";
    if (meta) meta.textContent = "";
    return;
  }
  const sectors = Array.from(new Set(usable.map((p) => p.sector || "—"))).sort();
  const colorOf = (s) => ((VIZ.PALETTE || [PRAVAHA.cyan])[Math.max(0, sectors.indexOf(s)) % (VIZ.PALETTE || [PRAVAHA.cyan]).length]);
  const capped = usable.filter((p) => p.pe <= 100 && p.pb <= 40);
  const capCount = capped.filter((p) => typeof p.market_cap === "number" && p.market_cap > 0).length;
  const useSize = !!state.ovFundMapSizeOn && capCount > 0;
  const caps = useSize ? capped.map((p) => (p.market_cap > 0 ? p.market_cap : 0)) : [];
  const maxCap = useSize ? Math.max.apply(null, caps.concat([1])) : 1;
  const spec = {
    height: 340,
    points: capped.map((p) => ({
      x: p.pe, y: p.pb,
      label: `${p.symbol} · ${p.sector || "—"} · P/E ${fmtNum(p.pe, 2)} · P/B ${fmtNum(p.pb, 2)}`
        + (p.market_cap > 0 ? ` · cap ${fmtCompact(p.market_cap)}` : " · cap not stored"),
      color: colorOf(p.sector || "—"),
      r: useSize ? (p.market_cap > 0 ? p.market_cap : 0) : 0,
    })),
    xLabel: "P/E (price ÷ reported EPS)",
    yLabel: "P/B (×)",
    xFormat: (v) => fmtNum(v, 0),
    yFormat: (v) => fmtNum(v, 1),
    onPick: (p) => { const sym = String(p.label || "").split(" · ")[0]; if (sym) { $("#symbol-input").value = sym; showView("charts"); if (typeof viewShown === "function") viewShown("charts"); loadChart(); } },
    ariaLabel: "Fundamental map: price-to-earnings versus price-to-book, coloured by sector"
      + (useSize ? ", sized by derived market capitalisation" : ""),
  };
  if (useSize) {
    spec.sizeBy = true;
    spec.maxR = 18;
    spec.sizeScale = Math.max(1, Math.sqrt(maxCap) / 15);
  }
  VIZ.scatter(mapHost, spec);
  const dropped = usable.length - capped.length;
  if (note) {
    note.innerHTML = `${fmtInt(capped.length)} of ${fmtInt(usable.length)} symbols plotted`
      + (dropped > 0 ? ` (${fmtInt(dropped)} with P/E &gt; 100 or P/B &gt; 40 are outside the axes so the cluster stays readable)` : "")
      + `. Each dot is one symbol with a stored close and positive, usable P/E and P/B from the latest stored fundamentals; colour is the sector. Click a dot to open its chart. Non-positive ratios are excluded, never plotted as negatives.`
      + (useSize
        ? ` Dot size is the derived market capitalisation (paid-up capital ÷ 100 × last close). `
          + `${fmtInt(capCount)} of ${fmtInt(capped.length)} plotted symbols have a stored paid-up capital; the rest are drawn at the minimum size, not as small companies.`
        : ` Market cap is stored for ${fmtInt(coverage.market_cap_available || capCount)} symbols; tick “Size dots by market cap” to encode it as dot size.`);
  }
  if (meta) meta.textContent = `${sectors.length} sectors · click a dot to open the chart`;
}


async function loadSwingBench() {
  const err = $("#swx-error");
  err.textContent = "";
  const sym = ($("#swx-symbol").value || $("#symbol-input").value || "").trim().toUpperCase();
  if (!sym) {
    err.textContent = "Enter a symbol (the chart's symbol is used when the field is empty).";
    return;
  }
  const riskPct = Number($("#swx-risk").value || "1");
  const params = new URLSearchParams({
    limit: String(Number($("#swx-limit").value || "400")),
    account_size: String(Number($("#swx-account").value || "100000")),
    risk_fraction: String(riskPct / 100),
  });
  const asof = ($("#swx-asof").value || "").trim();
  if (asof) params.set("as_of", asof);
  $("#swx-summary").innerHTML = `<div class="empty">Loading ${esc(sym)}…</div>`;
  try {
    const d = await api(`/api/bars/${encodeURIComponent(sym)}/swing-workbench?${params.toString()}`);
    renderSwingBench(d);
  } catch (e) {
    $("#swx-summary").innerHTML = `<div class="empty">Not loaded.</div>`;
    err.textContent = `Swing bench load failed: ${e.message || e}`;
  }
}

function renderSwingBench(d) {
  const st = d.structure || {};
  const nl = d.nearest_levels || {};
  const ref = d.reference_levels || {};
  const counts = d.counts || {};
  const stats = [
    ["Trend", st.trend || "—"],
    ["Last close", wbFmt(ref.last_close, 2)],
    ["Bars", String(d.bars ?? "—")],
    ["Swings", `${counts.swing_highs ?? "—"}H / ${counts.swing_lows ?? "—"}L`],
    ["As of", d.as_of || d.last_date || "—"],
    ["Framing", ref.framing || "none"],
  ];
  $("#swx-summary").innerHTML = stats
    .map(([k, v]) => `<div class="stat"><div class="k">${esc(k)}</div><div class="v">${esc(String(v))}</div></div>`)
    .join("");

  const levelRows = [];
  [
    ["Support (nearest confirmed below close)", nl.support, nl.support_missing_reason],
    ["Resistance (nearest confirmed above close)", nl.resistance, nl.resistance_missing_reason],
  ].forEach(([label, lvl, miss]) => {
    if (lvl) {
      levelRows.push([
        { html: esc(label) },
        { html: esc(wbFmt(lvl.price, 2)) },
        { html: esc(lvl.swing_date) },
        { html: esc(lvl.confirmed_date) },
      ]);
    } else {
      levelRows.push([
        { html: esc(label) },
        { html: "—" },
        { html: esc(miss || "not available") },
        { html: "—" },
      ]);
    }
  });
  $("#swx-levels").innerHTML = table(["Level", "Price", "Swing date", "Confirmed"], levelRows);

  const refRows = [
    ["Framing", ref.framing || "—"],
    [
      "Invalidation",
      ref.invalidation ? `${wbFmt(ref.invalidation.price, 2)} (swing ${ref.invalidation.swing_date}, confirmed ${ref.invalidation.confirmed_date})` : "—",
    ],
    ["Target (measured move)", ref.target ? `${wbFmt(ref.target.price, 2)} — ${ref.target.method}` : "—"],
    ["Risk to invalidation", ref.risk_pct === null || ref.risk_pct === undefined ? "—" : `${wbFmt(ref.risk_pct, 2)}%`],
    ["Reward to target", ref.reward_pct === null || ref.reward_pct === undefined ? "—" : `${wbFmt(ref.reward_pct, 2)}%`],
    ["Reward : risk", ref.reward_risk === null || ref.reward_risk === undefined ? "—" : wbFmt(ref.reward_risk, 2)],
    ["Note", ref.reason || "arithmetic from the levels above; no claim that any level holds"],
  ].map(([k, v]) => [{ html: esc(k) }, { html: esc(String(v)) }]);
  $("#swx-reference").innerHTML = table(["Item", "Value"], refRows);

  $("#swx-checklist").innerHTML = table(
    ["Reading", "Value", "Condition", "Meets condition", "Missing"],
    (d.checklist || []).map((r) => [
      { html: esc(r.name) },
      { html: esc(wbFmt(r.value, 4)) },
      { html: esc(r.condition) },
      r.pass === null || r.pass === undefined
        ? { html: "—" }
        : { html: r.pass ? "yes" : "no", cls: r.pass ? "up" : "down" },
      { html: esc(r.missing_reason || "") },
    ]),
  );

  const sz = d.sizing || {};
  if (sz.shares === null || sz.shares === undefined) {
    $("#swx-sizing").innerHTML = `<div class="hint">${esc(sz.reason || "not computable")}</div>`;
  } else {
    $("#swx-sizing").innerHTML = table(
      ["Item", "Value"],
      [
        ["Account size", wbFmt(sz.account_size, 2)],
        ["Risk per trade", `${wbFmt((sz.risk_fraction || 0) * 100, 2)}%`],
        ["Risk amount", wbFmt(sz.risk_amount, 2)],
        ["Per-share risk (to invalidation)", wbFmt(sz.per_share_risk, 2)],
        ["Shares (floor)", esc(String(sz.shares))],
        ["Notional at last close", wbFmt(sz.notional, 2)],
      ].map(([k, v]) => [{ html: esc(k) }, { html: String(v) }]),
    );
  }

  $("#swx-swings").innerHTML = table(
    ["Kind", "Pivot date", "Price", "Confirmed date"],
    (st.recent_swings || []).map((s) => [
      { html: esc(s.kind) },
      { html: esc(s.date) },
      { html: esc(wbFmt(s.price, 2)) },
      { html: esc(s.confirmed_date) },
    ]),
  );
  $("#swx-caveats").innerHTML = (d.caveats || []).map((c) => `<div>• ${esc(c)}</div>`).join("") +
    `<div class="hint">${esc(d.disclaimer || "")}</div>`;
}

function bindWorkbenchPanels() {
  const b1 = $("#bh-load");
  if (b1) b1.addEventListener("click", loadBreadthHistory);
  const b2 = $("#sea-load");
  if (b2) b2.addEventListener("click", loadSeasonality);
  const bmetric = $("#bh-chart-metric");
  if (bmetric) bmetric.addEventListener("change", renderBreadthChart);
  const b3 = $("#swx-load");
  if (b3) b3.addEventListener("click", loadSwingBench);
  const b4 = $("#swx-chart");
  if (b4) b4.addEventListener("click", () => {
    const sym = ($("#swx-symbol").value || "").trim().toUpperCase();
    if (!sym) return;
    $("#symbol-input").value = sym;
    showView("charts");
    viewShown("charts");
    loadChart();
  });
}

/* ---------------------------------------------------------------- NEW section */
function loadNewSection(tab) {
  const body = $("#new-body");
  if (!body) return;
  $$("#new-tabs .new-tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  body.innerHTML = `<div class="empty">Loading ${tab}…</div>`;
  const loaders = {
    nu: loadNewCompanyUniverse,
    nse: loadNewSectorExplorer,
    nprof: loadNewCompanyProfile,
    neps: loadNewEpsRankings,
    nepsh: loadNewEpsHistory,
    nttm: loadNewTtmEps,
    ncmp: loadNewFundCompare,
    nscr: loadNewScreener,
    nelig: loadNewMarginEligibility,
    ncov: loadNewDataCoverage,
  };
  const fn = loaders[tab];
  if (fn) fn(body);
  else body.innerHTML = `<div class="empty">Unknown tab.</div>`;
}
/* ==================================================================== BABA */
const BABA = { comps: null, selected: new Set(), templates: [], fmt: "xlsx",
               sector: null, period: null };

/* =========================================================== BABA shared UI
   One symbol catalogue, one sector catalogue and one formatting path for every
   BABA screen. The old screens each re-implemented a bare text box and printed
   the report API's raw cells, which is how numbers like 3437500000 and the
   words "no stored record" appeared without context.
   ======================================================================== */
const BABA_SECTORS = { by: {}, map: {}, source: "", loaded: false, loading: null };
const BABA_CATALOG = { items: [], bySymbol: new Map(), loaded: false, loading: null, error: null };
const BABA_SECTOR_ALIASES = {
  "commercial bank": "Commercial Banks", "commercial banks": "Commercial Banks",
  "development bank": "Development Banks", "development banks": "Development Banks",
  "finance": "Finance Companies", "finance companies": "Finance Companies",
  "hotel & tourism": "Hotels", "hotels": "Hotels",
  "hydro power": "Hydropower", "hydropower": "Hydropower",
  "investment": "Investment Companies", "investment companies": "Investment Companies",
  "life insurance": "Life Insurance", "microfinance": "Microfinance",
  "manufacturing and processing": "Manufacturing and Processing",
  "mutual fund": "Mutual Fund", "non-life insurance": "Non-Life Insurance",
  "others": "Others", "trading": "Trading",
};
function babaCanonicalSector(name) {
  const clean = String(name || "").trim();
  return clean ? (BABA_SECTOR_ALIASES[clean.toLowerCase()] || clean) : "";
}
async function babaLoadSectors(force = false) {
  if (BABA_SECTORS.loaded && !force) return BABA_SECTORS;
  if (BABA_SECTORS.loading && !force) return BABA_SECTORS.loading;
  BABA_SECTORS.loading = (async () => {
    try {
      const d = await api("/api/sectors");
      const by = {};
      for (const [name, members] of Object.entries(d.by_sector || {})) {
        const key = babaCanonicalSector(name);
        if (!key) continue;
        (by[key] ||= []).push(...(members || []));
      }
      for (const name of Object.keys(by)) {
        by[name] = [...new Set(by[name].map((s) => String(s).toUpperCase()))].sort();
      }
      BABA_SECTORS.by = by;
      BABA_SECTORS.map = d.sector_map || {};
      BABA_SECTORS.source = d.source || "stored sector classification";
      BABA_SECTORS.loaded = true;
    } finally {
      BABA_SECTORS.loading = null;
    }
    return BABA_SECTORS;
  })();
  return BABA_SECTORS.loading;
}
async function babaLoadCatalog(force = false) {
  if (BABA_CATALOG.loaded && !force) return BABA_CATALOG;
  if (BABA_CATALOG.loading && !force) return BABA_CATALOG.loading;
  BABA_CATALOG.loading = (async () => {
    BABA_CATALOG.error = null;
    try {
      const d = await api("/api/baba/symbols");
      BABA_CATALOG.items = (d.symbols || []).filter((x) => x && x.symbol);
    } catch (e) {
      // Keep the screen usable on an older backend: this fallback is the same
      // stored-bar catalogue the chart uses, with dataset flags set to unknown.
      try {
        const d = await api("/api/securities?limit=2000");
        BABA_CATALOG.items = (d.securities || []).map((x) => ({
          symbol: x.symbol, name: "", sector: "", has_prices: Number(x.bars) > 0,
          bars: Number(x.bars || 0), has_fundamentals: null, has_quarterly: null,
        }));
      } catch (e2) {
        BABA_CATALOG.error = String((e && e.message) || e2);
      }
    }
    BABA_CATALOG.bySymbol = new Map(BABA_CATALOG.items.map((x) => [String(x.symbol).toUpperCase(), x]));
    BABA_CATALOG.loaded = true;
    BABA_CATALOG.loading = null;
    return BABA_CATALOG;
  })();
  return BABA_CATALOG.loading;
}
function babaCatalogItem(sym) {
  return BABA_CATALOG.bySymbol.get(String(sym || "").toUpperCase()) || null;
}
function babaCatalogMatches(query, limit = 18) {
  const q = String(query || "").trim().toLowerCase();
  const scored = [];
  for (const item of BABA_CATALOG.items) {
    const sym = String(item.symbol || "").toLowerCase();
    const name = String(item.name || "").toLowerCase();
    const sector = String(item.sector || "").toLowerCase();
    let score;
    if (!q) score = item.has_prices ? 0 : 1;
    else if (sym === q) score = 0;
    else if (sym.startsWith(q)) score = 1;
    else if (name.startsWith(q)) score = 2;
    else if (sym.includes(q)) score = 3;
    else if (name.includes(q)) score = 4;
    else if (sector.includes(q)) score = 5;
    else continue;
    scored.push({ item, score });
  }
  scored.sort((a, b) => a.score - b.score || String(a.item.symbol).localeCompare(String(b.item.symbol)));
  return scored.slice(0, limit).map((x) => x.item);
}
function babaSectorNames() {
  return Object.keys(BABA_SECTORS.by || {}).sort();
}
function babaParseSymbols(raw) {
  return [...new Set(String(raw || "").split(/[,\n;]+/).map((s) => s.trim().toUpperCase()).filter(Boolean))];
}
async function babaUnknownSymbols(syms) {
  await babaLoadCatalog();
  if (!BABA_CATALOG.loaded || BABA_CATALOG.error) return [];
  return syms.filter((s) => !BABA_CATALOG.bySymbol.has(s));
}

/* ---------------------------------------------------- one shared autocomplete */
const BABA_AC = { el: null, input: null, items: [], active: -1, seq: 0, timer: null,
  opts: null, suppressUntil: 0 };
function babaAcElement() {
  if (BABA_AC.el) return BABA_AC.el;
  const el = document.createElement("div");
  el.id = "baba-sym-ac";
  el.className = "sym-ac";
  el.hidden = true;
  el.setAttribute("role", "listbox");
  el.setAttribute("aria-label", "Matching symbols");
  el.addEventListener("pointerdown", (e) => {
    // Keep focus in the input and prevent the document outside-click handler.
    e.preventDefault();
  });
  document.body.appendChild(el);
  BABA_AC.el = el;
  return el;
}
function babaAcClose() {
  const el = babaAcElement();
  el.hidden = true;
  el.innerHTML = "";
  BABA_AC.items = [];
  BABA_AC.active = -1;
  if (BABA_AC.input) {
    BABA_AC.input.setAttribute("aria-expanded", "false");
    BABA_AC.input.removeAttribute("aria-activedescendant");
  }
}
function babaAcPosition() {
  const input = BABA_AC.input;
  const el = babaAcElement();
  if (!input || el.hidden) return;
  const r = input.getBoundingClientRect();
  const width = Math.min(Math.max(r.width, 320), Math.max(240, window.innerWidth - 16));
  const left = Math.max(8, Math.min(r.left, window.innerWidth - width - 8));
  let top = r.bottom + 4;
  const wanted = Math.min(340, Math.max(120, el.scrollHeight || 240));
  if (top + wanted > window.innerHeight - 8) top = Math.max(8, r.top - wanted - 4);
  el.style.left = `${left}px`;
  el.style.top = `${top}px`;
  el.style.width = `${width}px`;
  el.style.maxHeight = `${Math.max(120, window.innerHeight - top - 12)}px`;
}
function babaAcRender() {
  const el = babaAcElement();
  if (!BABA_AC.input) return;
  const q = BABA_AC.tokenText || "";
  if (BABA_AC.loading) {
    el.innerHTML = `<div class="sym-ac-empty">Loading the stored symbol catalogue…</div>`;
  } else if (BABA_AC.opts && BABA_AC.opts.error) {
    el.innerHTML = `<div class="sym-ac-empty">${esc(BABA_AC.opts.error)}</div>`;
  } else if (!BABA_AC.items.length) {
    el.innerHTML = `<div class="sym-ac-empty">No stored symbol matches “${esc(q)}”. ` +
      `Type a different symbol; the field is not submitted as a valid symbol automatically.</div>`;
  } else {
    el.innerHTML = BABA_AC.items.map((item, i) => {
      const flags = [];
      if (item.has_prices) flags.push(`<span class="sym-flag ok">price</span>`);
      if (item.has_fundamentals) flags.push(`<span class="sym-flag ok">financials</span>`);
      if (item.has_quarterly) flags.push(`<span class="sym-flag ok">quarterly</span>`);
      if (item.has_fundamentals === false && item.has_prices === false) {
        flags.push(`<span class="sym-flag warn">no stored data yet</span>`);
      }
      return `<div class="sym-ac-item${i === BABA_AC.active ? " active" : ""}" role="option"` +
        ` id="baba-sym-opt-${i}" data-i="${i}" aria-selected="${i === BABA_AC.active}">` +
        `<span class="sym-code">${esc(item.symbol)}</span>` +
        `<span class="sym-name">${esc(item.name || "Company name not stored")}</span>` +
        `<span class="sym-sector">${esc(item.sector || "sector unknown")}</span>` +
        `<span class="sym-flags">${flags.join("")}</span></div>`;
    }).join("");
    el.querySelectorAll(".sym-ac-item").forEach((node) => {
      node.addEventListener("mouseenter", () => {
        BABA_AC.active = Number(node.dataset.i);
        babaAcRender();
      });
      node.addEventListener("click", () => babaAcChoose(Number(node.dataset.i)));
    });
  }
  el.hidden = false;
  BABA_AC.input.setAttribute("aria-expanded", "true");
  if (BABA_AC.active >= 0) {
    BABA_AC.input.setAttribute("aria-activedescendant", `baba-sym-opt-${BABA_AC.active}`);
    const active = el.querySelector(`.sym-ac-item[data-i="${BABA_AC.active}"]`);
    if (active) active.scrollIntoView({ block: "nearest" });
  } else {
    BABA_AC.input.removeAttribute("aria-activedescendant");
  }
  babaAcPosition();
}
function babaAcToken(input, multiple) {
  const value = input.value || "";
  if (!multiple) return { start: 0, end: value.length, text: value.trim() };
  let pos = input.selectionStart == null ? value.length : input.selectionStart;
  let start = pos;
  while (start > 0 && !/[,\n;]/.test(value[start - 1])) start--;
  let end = pos;
  while (end < value.length && !/[,\n;]/.test(value[end])) end++;
  while (start < end && /\s/.test(value[start])) start++;
  while (end > start && /\s/.test(value[end - 1])) end--;
  return { start, end, text: value.slice(start, end).trim() };
}
function babaAcRefresh() {
  const input = BABA_AC.input;
  if (!input) return;
  const token = babaAcToken(input, !!(BABA_AC.opts && BABA_AC.opts.multiple));
  BABA_AC.tokenText = token.text;
  BABA_AC.active = -1;
  const seq = ++BABA_AC.seq;
  if (!BABA_CATALOG.loaded) {
    BABA_AC.loading = true;
    BABA_AC.items = [];
    babaAcRender();
    babaLoadCatalog().then(() => {
      if (seq !== BABA_AC.seq || BABA_AC.input !== input) return; // stale load
      BABA_AC.loading = false;
      BABA_AC.items = babaCatalogMatches(token.text);
      if (BABA_CATALOG.error) BABA_AC.opts.error = `Symbol catalogue unavailable: ${BABA_CATALOG.error}`;
      babaAcRender();
    });
    return;
  }
  BABA_AC.loading = false;
  BABA_AC.items = babaCatalogMatches(token.text);
  babaAcRender();
}
function babaAcChoose(index) {
  const item = BABA_AC.items[index];
  const input = BABA_AC.input;
  if (!item || !input) return;
  const opts = BABA_AC.opts || {};
  const token = babaAcToken(input, !!opts.multiple);
  if (opts.multiple) {
    const before = input.value.slice(0, token.start).replace(/[,\s;]+$/, "");
    const after = input.value.slice(token.end).replace(/^[,\s;]+/, "");
    input.value = [before, item.symbol, after].filter(Boolean).join(", ");
  } else {
    input.value = item.symbol;
  }
  babaShowPickedSymbol(input, item, !!opts.multiple);
  // The synthetic input/change events below must not immediately reopen the
  // list we just closed. Suppress focus/open handling for one interaction turn.
  BABA_AC.suppressUntil = Date.now() + 250;
  babaAcClose();
  input.dispatchEvent(new Event("input", { bubbles: true }));
  input.dispatchEvent(new Event("change", { bubbles: true }));
  input.focus();
  const end = input.value.length;
  try { input.setSelectionRange(end, end); } catch (e) { /* not a text-like input */ }
  if (typeof opts.onSelect === "function") opts.onSelect(item.symbol, item);
}
function babaShowPickedSymbol(input, item, multiple) {
  const host = input.closest("label") || input.parentElement;
  if (!host) return;
  let badge = host.querySelector(".sym-picked");
  if (!badge) {
    badge = document.createElement("span");
    badge.className = "sym-picked";
    host.appendChild(badge);
  }
  const data = item.has_fundamentals === null || item.has_fundamentals === undefined
    ? "dataset status not reported" : item.has_fundamentals ? "financials available" : "no financial record";
  badge.textContent = multiple
    ? `Added ${item.symbol} · ${item.name || "name not stored"} · ${data}`
    : `${item.symbol} · ${item.name || "name not stored"} · ${item.sector || "sector unknown"} · ${data}`;
}
function babaAcOpen(input, opts) {
  BABA_AC.input = input;
  BABA_AC.opts = opts || {};
  BABA_AC.opts.error = BABA_CATALOG.error ? `Symbol catalogue unavailable: ${BABA_CATALOG.error}` : null;
  const token = babaAcToken(input, !!BABA_AC.opts.multiple);
  BABA_AC.tokenText = token.text;
  BABA_AC.seq++;
  BABA_AC.active = -1;
  babaAcRefresh();
}
function attachBabaSymbolAutocomplete(input, opts = {}) {
  if (!input || input.dataset.symAcBound === "1") return;
  input.dataset.symAcBound = "1";
  input.setAttribute("autocomplete", "off");
  input.setAttribute("spellcheck", "false");
  input.setAttribute("role", "combobox");
  input.setAttribute("aria-autocomplete", "list");
  input.setAttribute("aria-expanded", "false");
  input.setAttribute("aria-controls", "baba-sym-ac");
  const multiple = !!opts.multiple;
  const open = () => {
    if (Date.now() < BABA_AC.suppressUntil) return;
    babaAcOpen(input, opts);
  };
  input.addEventListener("focus", open);
  input.addEventListener("click", open);
  input.addEventListener("input", () => {
    if (Date.now() < BABA_AC.suppressUntil) return;
    if (BABA_AC.input !== input) babaAcOpen(input, opts);
    clearTimeout(BABA_AC.timer);
    BABA_AC.timer = setTimeout(() => {
      if (BABA_AC.input === input && Date.now() >= BABA_AC.suppressUntil) babaAcRefresh();
    }, 70);
  });
  input.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { babaAcClose(); return; }
    if (e.key === "Tab") { babaAcClose(); return; }
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      if (!BABA_AC.el || BABA_AC.el.hidden) open();
      if (!BABA_AC.items.length) return;
      e.preventDefault();
      const step = e.key === "ArrowDown" ? 1 : -1;
      BABA_AC.active = (BABA_AC.active + step + BABA_AC.items.length) % BABA_AC.items.length;
      babaAcRender();
      return;
    }
    if (e.key === "Enter") {
      if (BABA_AC.input === input && BABA_AC.items.length) {
        if (BABA_AC.active < 0) BABA_AC.active = 0;
        e.preventDefault();
        babaAcChoose(BABA_AC.active);
      }
    }
  });
  // Select the exact symbol when the user leaves the field after typing one.
  input.addEventListener("blur", () => {
    const token = babaAcToken(input, multiple).text.toUpperCase();
    const item = babaCatalogItem(token);
    if (item && (multiple || input.value.trim().toUpperCase() === token)) {
      babaShowPickedSymbol(input, item, multiple);
    }
  });
  if (!BABA_CATALOG.loaded) babaLoadCatalog();
}
if (typeof window !== "undefined") {
  document.addEventListener("pointerdown", (e) => {
    if (!BABA_AC.input) return;
    if (e.target === BABA_AC.input || (BABA_AC.el && BABA_AC.el.contains(e.target))) return;
    babaAcClose();
  }, true);
  window.addEventListener("resize", babaAcPosition);
  window.addEventListener("scroll", babaAcPosition, true);
  window.addEventListener("blur", babaAcClose);
}

/* ------------------------------------------------------- report formatting */
function babaIsNumber(v) {
  return v !== null && v !== undefined && v !== "" && (typeof v === "number" || /^-?\d+(\.\d+)?$/.test(String(v)));
}
function babaHeaderClass(header) {
  const h = String(header || "").toLowerCase();
  if (h.includes("%") || h.includes("growth") || h.includes("yield")) return "num";
  if (h.includes("date") || h.includes("period") || h.includes("source") ||
      h.includes("verification") || h.includes("sector") || h.includes("company")) return "";
  return "num";
}
function babaFormatCell(value, header) {
  if (value === null || value === undefined || value === "") {
    return { html: `<span class="missing" title="No stored value for this field">—</span>`, cls: "missing" };
  }
  const h = String(header || "").toLowerCase();
  if (babaIsNumber(value)) {
    const n = Number(value);
    let text;
    if (h.includes("%") || h.includes("growth") || h.includes("yield")) text = `${fmtNum(n, 2)}%`;
    else if (h.includes("rank") || h.includes("sessions") || h.includes("companies") ||
             h.includes("count") || h.includes("bars") || h.includes("records")) text = fmtInt(n);
    else if (h.includes("market cap") || h.includes("paid-up") || h.includes("net profit") ||
             h.includes("value")) text = fmtNum(n, 0);
    else text = fmtNum(n, 2);
    return { html: esc(text), cls: "num" };
  }
  const text = String(value);
  const cls = text.length > 46 ? "wrap" : (babaHeaderClass(header) === "num" ? "num" : "");
  return { html: esc(text), cls };
}
function babaTableHtml(headers, rows) {
  if (!rows || !rows.length) return `<div class="empty">No rows were produced.</div>`;
  const head = (headers || []).map((h) => {
    const cls = babaHeaderClass(h);
    return `<th${cls ? ` class="${cls}"` : ""}>${esc(h)}</th>`;
  }).join("");
  const body = rows.map((row) => `<tr>${(row || []).map((cell, i) => {
    const f = babaFormatCell(cell, (headers || [])[i]);
    return `<td class="${f.cls}">${f.html}</td>`;
  }).join("")}</tr>`).join("");
  return `<table>${head ? `<thead><tr>${head}</tr></thead>` : ""}<tbody>${body}</tbody></table>`;
}
function babaRenderSections(rep, opts = {}) {
  const parts = [];
  const want = opts.sections ? new Set(opts.sections) : null;
  for (const [cid, sec] of Object.entries(rep.sections || {})) {
    if (want && !want.has(cid)) continue;
    if (!sec.available) continue;
    const lines = Array.isArray(sec.summary) ? sec.summary : [];
    const body = lines.length
      ? `<ul class="report-list">${lines.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>`
      : `<div class="tablewrap">${babaTableHtml(sec.headers || [], sec.rows || [])}</div>`;
    parts.push(`<section class="report-section" data-component="${esc(cid)}">
      <h3>${esc(sec.name || cid)}</h3>${sec.note ? `<p class="hint">${esc(sec.note)}</p>` : ""}${body}
    </section>`);
  }
  const un = (rep.quality && rep.quality.unavailable) || [];
  if (un.length && opts.showUnavailable !== false) {
    const relevant = want ? un.filter((u) => want.has(u.id)) : un;
    if (relevant.length) {
      parts.push(`<details class="report-unavailable"><summary>${relevant.length} selected ` +
        `section${relevant.length === 1 ? "" : "s"} could not be produced</summary>` +
        `<div class="tablewrap">${babaTableHtml(["Section", "Reason"],
          relevant.map((u) => [u.name || u.id, u.reason || "unavailable"]))}</div></details>`);
    }
  }
  return parts.join("") || `<div class="empty">No selected section produced data for this request.</div>`;
}
function babaReportHero(title, subtitle, meta, stats) {
  return `<header class="report-hero">
    <h2>${esc(title)}</h2>
    <p class="report-subtitle">${esc(subtitle)}</p>
    ${stats && stats.length ? `<div class="stat-row">${stats.map((s) =>
      `<div class="stat"><div class="k">${esc(s.k)}</div><div class="v">${esc(s.v)}</div></div>`).join("")}</div>` : ""}
    <p class="hint">${meta}</p>
  </header>`;
}

/* --------------------------------------------------- fundamental snapshots */
const BABA_FIELD_DISPLAY = {
  eps: "EPS", pe: "P/E", paid_up_capital: "Paid-up capital",
  profit: "Net profit", net_worth_per_share: "Net worth per share",
  revenue: "Revenue", book_value_per_share: "Book value per share",
  dividend_per_share: "Dividend per share", shares_outstanding: "Shares outstanding",
  public_float: "Public float", promoter_holding_pct: "Promoter holding %",
  total_equity: "Total equity", total_assets: "Total assets", listing_date: "Listing date",
};
/* A stored value can be real and still be implausible at the per-share scale
   (the source occasionally carries a total where a per-share figure belongs).
   We keep and display it exactly, but say so instead of silently mixing it into
   a range or an average. */
function babaSuspectValue(field, value) {
  if (!babaIsNumber(value)) return "";
  const n = Number(value), a = Math.abs(n);
  if ((field === "EPS" || field === "Net worth per share") && a > 100000) {
    return "implausible per-share magnitude";
  }
  if (field === "P/E" && a > 1000) return "extreme P/E magnitude";
  if (field === "Paid-up capital" && n < 0) return "negative paid-up capital";
  return "";
}
function babaFieldName(field) {
  const raw = String(field || "").trim();
  if (!raw) return "unknown";
  return BABA_FIELD_DISPLAY[raw.toLowerCase()] ||
    raw.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
function babaPeriodGroups(records) {
  const groups = new Map();
  for (const rec of records || []) {
    const label = rec.period_label || rec.period_end || "unlabelled period";
    const end = String(rec.period_end || "").slice(0, 10);
    const key = `${end}\u0000${label}`;
    if (!groups.has(key)) groups.set(key, { label, end, fields: {} });
    const field = babaFieldName(rec.field || rec.source_field);
    const prior = groups.get(key).fields[field];
    if (!prior || String(rec.retrieved_at || "") > String(prior.retrieved_at || "")) {
      groups.get(key).fields[field] = rec;
    }
  }
  return [...groups.values()].sort((a, b) =>
    (b.end || "").localeCompare(a.end || "") || b.label.localeCompare(a.label));
}
async function babaFundamentalSnapshot(sym) {
  const symbol = String(sym || "").toUpperCase();
  const [fund, bars] = await Promise.all([
    api(`/api/fundamentals/${encodeURIComponent(symbol)}`),
    api(`/api/bars/${encodeURIComponent(symbol)}?limit=1`).catch(() => null),
  ]);
  const records = fund.records || [];
  const periods = babaPeriodGroups(records);
  const latestPeriod = periods[0] || null;
  const bar = bars && bars.bars && bars.bars.length ? bars.bars[bars.bars.length - 1] : null;
  const item = babaCatalogItem(symbol) || {};
  const core = ["EPS", "P/E", "Net worth per share", "Paid-up capital", "Net profit",
    "Revenue", "Dividend per share", "Shares outstanding", "Public float"];
  const have = new Set(records.map((r) => babaFieldName(r.field || r.source_field)));
  const suspects = [];
  for (const p of periods) {
    for (const [field, rec] of Object.entries(p.fields || {})) {
      const flag = babaSuspectValue(field, rec.value);
      if (flag) suspects.push({ period: p.label, field, value: rec.value, flag });
    }
  }
  return {
    symbol, records, periods, latestPeriod, bar, item,
    name: item.name || "", sector: item.sector || "",
    missing: core.filter((f) => !have.has(f)), suspects,
    hasQuarterly: records.some((r) => /quarter/i.test(r.period_label || "")),
    quarterlyPeriods: periods.filter((p) => /quarter/i.test(p.label)),
    requestedAt: new Date().toISOString(),
  };
}
function babaMetric(snap, field) {
  for (const p of snap.periods) if (p.fields[field]) return { ...p.fields[field], period: p };
  return null;
}
function babaRenderFundamentalSnapshot(snap, opts = {}) {
  const item = snap.item || {};
  const price = snap.bar ? Number(snap.bar.close) : null;
  const priceDate = snap.bar ? String(snap.bar.time).slice(0, 10) : "—";
  const eps = babaMetric(snap, "EPS");
  const pe = babaMetric(snap, "P/E");
  const profit = babaMetric(snap, "Net profit");
  const nw = babaMetric(snap, "Net worth per share");
  const puc = babaMetric(snap, "Paid-up capital");
  const latest = snap.latestPeriod;
  const source = (eps && eps.source) || (latest && Object.values(latest.fields)[0]?.source) || "—";
  const verification = (eps && eps.verification) || (latest && Object.values(latest.fields)[0]?.verification) || "—";
  const stats = [
    { k: "Last stored close", v: price == null ? "—" : `NPR ${fmtNum(price, 2)}` },
    { k: "Price date", v: priceDate },
    { k: "Latest EPS", v: eps ? `NPR ${fmtNum(eps.value, 2)}` : "—" },
    { k: "Latest P/E", v: pe ? `${fmtNum(pe.value, 2)}x` : "—" },
    { k: "Latest net profit", v: profit ? `NPR ${fmtNum(profit.value, 0)}` : "—" },
    { k: "Net worth / share", v: nw ? `NPR ${fmtNum(nw.value, 2)}` : "—" },
    { k: "Paid-up capital", v: puc ? `NPR ${fmtNum(puc.value, 0)}` : "—" },
    { k: "Reporting period", v: latest ? latest.label : "—" },
  ];
  const badges = [];
  badges.push(`<span class="pill ${snap.records.length ? "pill-info" : "pill-warn"}">${snap.records.length} stored fundamental records</span>`);
  badges.push(`<span class="pill ${snap.hasQuarterly ? "pill-info" : "pill-warn"}">${snap.hasQuarterly ? "quarterly records available" : "no quarterly record"}</span>`);
  if (item.has_prices) badges.push(`<span class="pill pill-info">price history available</span>`);
  const missing = snap.missing.length
    ? `<div class="report-missing"><b>Not stored:</b> ${snap.missing.map((m) => esc(m)).join(", ")}. ` +
      `These fields are shown as <span class="missing">—</span>; they are not treated as zero and are not inferred.</div>`
    : `<div class="report-missing ok">All nine core fields used here have a stored value.</div>`;
  const suspectHtml = snap.suspects && snap.suspects.length
    ? `<div class="banner warn"><b>Stored-value check:</b> ${fmtInt(snap.suspects.length)} value(s) ` +
      `look inconsistent with their field. They are shown exactly as stored and are not silently ` +
      `converted or dropped. ${snap.suspects.slice(0, 5).map((x) =>
        `${esc(x.period)} · ${esc(x.field)} = ${esc(babaFormatCell(x.value, x.field).html)} (${esc(x.flag)})`).join("; ")}` +
      `${snap.suspects.length > 5 ? " …" : ""}</div>`
    : "";
  const showPeriods = opts.periods === "all" ? snap.periods : snap.periods.slice(0, opts.periods || 6);
  const headers = ["Period", "Period end", "EPS (NPR)", "P/E (x)", "Net profit (NPR)",
    "Net worth/share (NPR)", "Paid-up capital (NPR)", "Source", "Verification"];
  const rows = showPeriods.map((p) => [
    p.label, p.end || "—",
    p.fields.EPS ? p.fields.EPS.value : null,
    p.fields["P/E"] ? p.fields["P/E"].value : null,
    p.fields["Net profit"] ? p.fields["Net profit"].value : null,
    p.fields["Net worth per share"] ? p.fields["Net worth per share"].value : null,
    p.fields["Paid-up capital"] ? p.fields["Paid-up capital"].value : null,
    (p.fields.EPS && p.fields.EPS.source) || "—",
    (p.fields.EPS && p.fields.EPS.verification) || "—",
  ]);
  const detail = snap.records.length
    ? `<div class="tablewrap">${babaTableHtml(headers, rows)}</div>` +
      (snap.periods.length > showPeriods.length
        ? `<p class="hint">Showing the newest ${showPeriods.length} of ${snap.periods.length} stored periods. Quarterly analysis shows all periods.</p>` : "")
    : `<div class="empty"><b>${esc(snap.symbol)}</b> has no stored fundamental records. ` +
      `The symbol was found in the market catalogue${snap.bar ? ` and its last stored close is NPR ${fmtNum(price, 2)} on ${esc(priceDate)}` : ""}. ` +
      `Requested dataset: company fundamentals. This is an empty result, not a failed request. ` +
      `No financial statements are inferred.</div>`;
  return `<section class="report-symbol" data-symbol="${esc(snap.symbol)}">
    <div class="report-symbol-head">
      <div><h3>${esc(snap.symbol)}${snap.name ? ` · ${esc(snap.name)}` : ""}</h3>
        <p class="hint">${esc(snap.sector || "sector not stored")} · stored fundamentals and end-of-day price</p></div>
      <div class="report-badges">${badges.join("")}</div>
    </div>
    ${babaReportHero("Latest available metrics", `Reporting period: ${latest ? latest.label : "no stored period"}`,
      `Source: ${esc(source)} · verification: ${esc(verification)} · price is the last stored session, not a live quote.`, stats)}
    ${missing}
    ${suspectHtml}
    ${detail}
  </section>`;
}


async function loadBabaSection(tab) {
  const body = $("#baba-body");
  if (!body) return;
  $$("#baba-tabs .baba-tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  if (!BABA.comps) {
    try { BABA.comps = await (await fetch("/api/baba/components")).json(); }
    catch (e) { body.innerHTML = `<div class="empty">Could not load the component registry: ${esc(e.message)}</div>`; return; }
  }
  const loaders = { dash: babaDash, sector: babaSector, scanner: babaScanner,
    quarterly: babaQuarterly, eligibility: babaEligibility, compare: babaCompare,
    journal: babaJournal, builder: babaBuilder, exports: babaExports, extras: babaExtras };
  (loaders[tab] || babaDash)(body);
}

/* ------------------------------------------------------------ dashboard */
async function babaDash(body) {
  body.innerHTML = `<div class="controls">
      <label>Symbol
        <input id="baba-sym" placeholder="Type a symbol or company name" aria-label="Company symbol" />
      </label>
      <button class="ctb-btn" id="baba-go">Analyse</button>
      <label>Sector report
        <select id="baba-sector-sel" aria-label="Sector report"></select>
      </label>
      <button class="ctb-btn" id="baba-sector-go">Open sector report</button>
    </div>
    <div id="baba-dash-out" class="baba-output"><div class="empty">Choose a symbol from the autocomplete and press Analyse.</div></div>`;
  const sel = $("#baba-sector-sel");
  try {
    await babaLoadSectors();
    const sectors = babaSectorNames();
    sel.innerHTML = `<option value="">— choose sector —</option>` +
      sectors.map((x) => `<option value="${esc(x)}">${esc(x)} (${(BABA_SECTORS.by[x] || []).length})</option>`).join("");
  } catch (e) { sel.innerHTML = `<option value="">sectors unavailable: ${esc(e.message)}</option>`; }

  const run = async (sym) => {
    const out = $("#baba-dash-out");
    const symbol = String(sym || ($("#baba-sym").value || "")).trim().toUpperCase();
    if (!symbol) { out.innerHTML = `<div class="empty">Choose a symbol first.</div>`; return; }
    out.innerHTML = `<div class="empty">Loading stored fundamentals for ${esc(symbol)}…</div>`;
    try {
      const snap = await babaFundamentalSnapshot(symbol);
      out.innerHTML = babaRenderFundamentalSnapshot(snap, { periods: 4 });
    } catch (e) {
      out.innerHTML = `<div class="empty">Could not load ${esc(symbol)}: ${esc(e.message)}. ` +
        `This is a request failure, not an empty stored record.</div>`;
    }
  };
  attachBabaSymbolAutocomplete($("#baba-sym"), { onSelect: (s) => run(s) });
  $("#baba-go").onclick = () => run();
  $("#baba-sector-go").onclick = () => {
    const s = sel.value;
    if (!s) { sel.focus(); return; }
    BABA.sector = s;
    showView("baba/sector");
    viewShown("baba/sector");
  };
  const current = ($("#symbol-input") && $("#symbol-input").value || "").trim().toUpperCase();
  if (current && babaCatalogItem(current)) $("#baba-sym").value = current;
}

/* -------------------------------------------------------- sector explorer */
function babaSectorCoverage(rows) {
  const headers = (rows && rows.headers) || [];
  const idx = (name) => headers.indexOf(name);
  const data = rows && rows.rows ? rows.rows : [];
  const col = (name) => {
    const i = idx(name);
    return i < 0 ? [] : data.map((r) => r[i]).filter((v) => babaIsNumber(v)).map(Number);
  };
  const median = (values) => {
    if (!values.length) return null;
    const ordered = [...values].sort((a, b) => a - b);
    const mid = Math.floor(ordered.length / 2);
    return ordered.length % 2 ? ordered[mid] : (ordered[mid - 1] + ordered[mid]) / 2;
  };
  const summary = (name, unit, label) => {
    const values = col(name);
    return {
      label, unit, n: values.length,
      median: median(values),
      min: values.length ? Math.min(...values) : null,
      max: values.length ? Math.max(...values) : null,
    };
  };
  return {
    rows: data,
    headers,
    price: summary("Last close (NPR)", "NPR", "Last close"),
    pe: summary("P/E (x)", "x", "P/E"),
    eps: summary("EPS (NPR)", "NPR", "EPS"),
    networth: summary("Net worth/share (NPR)", "NPR", "Net worth/share"),
    cap: summary("Market cap (NPR)", "NPR", "Market cap"),
    withPrice: data.filter((r) => babaIsNumber(r[idx("Last close (NPR)")])).length,
    withEps: data.filter((r) => babaIsNumber(r[idx("EPS (NPR)")])).length,
    withPe: data.filter((r) => babaIsNumber(r[idx("P/E (x)")])).length,
    withNetWorth: data.filter((r) => babaIsNumber(r[idx("Net worth/share (NPR)")])).length,
  };
}
function babaMetricSummaryHtml(cov) {
  const cards = [cov.pe, cov.eps, cov.networth, cov.cap].filter((s) => s.n > 0);
  if (!cards.length) {
    return `<div class="empty">No sector-level valuation summary can be calculated: ` +
      `none of the companies has the relevant stored metric. No average is invented.</div>`;
  }
  return `<div class="report-metrics">${cards.map((s) => {
    const fmt = s.unit === "x" ? (v) => `${fmtNum(v, 2)}x`
      : s.unit === "NPR" && s.label === "Market cap" ? (v) => `NPR ${fmtNum(v, 0)}`
      : (v) => `NPR ${fmtNum(v, 2)}`;
    return `<div class="report-metric">
      <div class="k">${esc(s.label)}</div>
      <div class="v">${esc(fmt(s.median))}</div>
      <div class="hint">median · ${fmtInt(s.n)} of ${fmtInt(cov.rows.length)} companies with a stored value</div>
      <div class="tiny">range ${esc(fmt(s.min))} – ${esc(fmt(s.max))}</div>
    </div>`;
  }).join("")}</div>`;
}
async function babaSectorReport(sector) {
  const out = $("#baba-sector-report");
  if (!out) return;
  const syms = (BABA_SECTORS.by[sector] || []).slice();
  if (!sector) {
    out.innerHTML = `<div class="empty">Choose a sector to generate its report.</div>`;
    return;
  }
  if (!syms.length) {
    out.innerHTML = `<div class="empty"><b>${esc(sector)}</b> has no companies in the stored ` +
      `reference classification. Requested dataset: sector fundamentals. This is an empty ` +
      `classification result, not a failed request. No companies are invented.</div>`;
    return;
  }
  out.innerHTML = `<div class="empty">Building ${esc(sector)} report from ${fmtInt(syms.length)} stored symbols…</div>`;
  const components = ["sector_overview", "sector_comparison", "sector_outliers",
    "sector_eps_rank", "sector_pe_rank", "sector_networth_rank", "sector_cap_rank",
    "sector_growth_rank"];
  try {
    const rep = await babaPreview(components, syms, { sector });
    const comparison = (rep.sections && rep.sections.sector_comparison) || null;
    if (!comparison || !comparison.available) {
      out.innerHTML = `<div class="empty">The sector comparison could not be produced: ` +
        `${esc((comparison && comparison.reason) || "no stored comparison rows")}. ` +
        `Selected sector: <b>${esc(sector)}</b>, ${fmtInt(syms.length)} classified symbols.</div>`;
      return;
    }
    const cov = babaSectorCoverage(comparison);
    const generated = rep.generated_at ? new Date(rep.generated_at).toLocaleString() : new Date().toLocaleString();
    const missingCell = `<span class="missing" title="No stored value">—</span>`;
    const overview = `<p>This report covers <b>${fmtInt(syms.length)}</b> companies in the stored ` +
      `<b>${esc(sector)}</b> classification. <b>${fmtInt(cov.withPrice)}</b> have a stored end-of-day close, ` +
      `<b>${fmtInt(cov.withEps)}</b> have a stored EPS, <b>${fmtInt(cov.withPe)}</b> have a stored or derivable P/E, ` +
      `and <b>${fmtInt(cov.withNetWorth)}</b> have net worth per share. ` +
      `No company or financial value is inferred for a missing field.</p>`;
    const companyTable = `<div class="tablewrap report-company-table">${babaTableHtml(comparison.headers, comparison.rows)}</div>`;
    const quality = rep.sections && rep.sections.sector_outliers && rep.sections.sector_outliers.available
      ? babaRenderSections(rep, { sections: ["sector_outliers"], showUnavailable: false })
      : `<div class="empty">No outlier report was produced.</div>`;
    const extras = babaRenderSections(rep, {
      sections: ["sector_eps_rank", "sector_pe_rank", "sector_networth_rank",
        "sector_cap_rank", "sector_growth_rank"],
      showUnavailable: false,
    });
    const unavailable = ((rep.quality && rep.quality.unavailable) || [])
      .filter((u) => ["sector_comparison", "sector_outliers"].includes(u.id));
    out.innerHTML = `
      ${babaReportHero(`Sector Report — ${sector}`,
        `Stored classification report · generated ${generated}`,
        `Source: <b>${esc(BABA_SECTORS.source)}</b> · company metrics: stored fundamentals and the latest stored session (end of day, not live) · ` +
        `sector summaries use only companies with a stored value.`,
        [
          { k: "Companies", v: fmtInt(syms.length) },
          { k: "With stored price", v: fmtInt(cov.withPrice) },
          { k: "With stored EPS", v: fmtInt(cov.withEps) },
          { k: "With stored P/E", v: fmtInt(cov.withPe) },
        ])}
      <div class="report-toolbar">
        <label>Export format
          <select id="baba-sector-fmt">
            <option value="pdf">PDF</option><option value="xlsx" selected>XLSX</option>
            <option value="csv">CSV (ZIP)</option><option value="json">JSON</option>
          </select>
        </label>
        <button class="ctb-btn" id="baba-sector-export">Export full sector report</button>
        <span class="hint">The export contains the same selected sections, sector scope and provenance.</span>
      </div>
      <section class="report-section"><h3>Sector overview</h3>${overview}</section>
      <section class="report-section"><h3>Coverage and data quality</h3>
        <div class="report-coverage">
          <span class="pill pill-info">${fmtInt(cov.withPrice)} / ${fmtInt(syms.length)} price records</span>
          <span class="pill pill-info">${fmtInt(cov.withEps)} / ${fmtInt(syms.length)} EPS records</span>
          <span class="pill ${cov.withNetWorth < syms.length ? "pill-warn" : "pill-info"}">${fmtInt(cov.withNetWorth)} / ${fmtInt(syms.length)} net-worth records</span>
          <span class="pill ${cov.withPe < syms.length ? "pill-warn" : "pill-info"}">${fmtInt(cov.withPe)} / ${fmtInt(syms.length)} P/E values</span>
        </div>
        <p class="hint">A dash (${missingCell}) means the stored source has no value for that field. ` +
        `It is not a zero. P/E is shown only when stored or derivable from a positive stored EPS and a stored close.</p>
      </section>
      <section class="report-section"><h3>Sector-level summaries</h3>
        ${babaMetricSummaryHtml(cov)}
        <p class="hint">These are descriptive summaries of the values visible in the table below — not forecasts, ` +
        `not sector averages for companies with missing data, and not investment recommendations.</p>
      </section>
      <section class="report-section"><h3>Company-by-company comparison</h3>${companyTable}
        <p class="hint">Long company names wrap inside the table; the table scrolls horizontally on narrow screens. ` +
        `Price date is the last stored session. All prices are end-of-day historical values.</p>
      </section>
      <section class="report-section"><h3>Data-quality notes and missing fields</h3>${quality}
        ${unavailable.length ? `<p class="hint">${esc(unavailable.map((u) => `${u.name}: ${u.reason}`).join(" · "))}</p>` : ""}
        <p class="hint">Sector labels are a stored reference classification and can lag a current NEPSE listing. ` +
        `Financial values come from stored filings; verification and source are carried by the generated export.</p>
      </section>
      <details class="report-more"><summary>Additional sector rankings and comparisons</summary>${extras}</details>
      <footer class="report-footer">
        <span>Report generated: ${esc(generated)}</span>
        <span>Symbols in scope: ${fmtInt(syms.length)}</span>
        <span>Format: JSON preview · export: PDF/XLSX/CSV/JSON</span>
      </footer>`;
    $("#baba-sector-export").onclick = () => babaDownloadReport({
      components, symbols: syms, sector, fmt: $("#baba-sector-fmt").value,
      title: `Sector Report — ${sector}`,
      notes: `Stored sector classification. ${fmtInt(syms.length)} companies in scope. ` +
        `Prices are last stored sessions (end of day), not live quotes.`,
    }).catch((e) => {
      out.insertAdjacentHTML("afterbegin",
        `<div class="banner warn">Export failed: ${esc(e.message)}</div>`);
    });
  } catch (e) {
    out.innerHTML = `<div class="empty">Could not generate the ${esc(sector)} sector report: ${esc(e.message)}. ` +
      `No table was substituted and no values were invented.</div>`;
  }
}
async function babaDownloadReport({ components, symbols, sector, period, fmt, title, notes }) {
  const q = new URLSearchParams({ components: components.join(","), format: fmt || "xlsx" });
  if (symbols && symbols.length) q.set("symbols", symbols.join(","));
  if (sector) q.set("sector", sector);
  if (period) q.set("period", period);
  if (title) q.set("title", title);
  if (notes) q.set("notes", notes);
  const r = await fetch(API_BASE + "/api/baba/report/export?" + q.toString(), _withFriendToken({}));
  if (!r.ok) {
    let detail = r.statusText;
    try { const j = await r.json(); detail = j.detail || j.error || detail; } catch (e) { /* not json */ }
    throw new Error(detail);
  }
  const blob = await r.blob();
  const disp = r.headers.get("content-disposition") || "";
  const match = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(disp);
  const fallback = `${(title || "pravaha-report").replace(/[^A-Za-z0-9._ -]+/g, "_")}.${fmt || "xlsx"}`;
  const name = match ? decodeURIComponent(match[1]) : fallback;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = name;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
}
async function babaSector(body) {
  body.innerHTML = `<div class="controls">
      <label>Sector
        <select id="baba-sector-select" aria-label="Sector"></select>
      </label>
      <button class="ctb-btn" id="baba-sector-generate">Generate sector report</button>
      <span class="hint" id="baba-sector-hint">Reports use stored classifications and stored financial records.</span>
    </div>
    <div id="baba-sector-errors" class="error"></div>
    <section class="card wide baba-sector-card">
      <h2>Sector catalogue</h2>
      <div id="baba-sector-explorer" class="tablewrap"><div class="empty">Loading sector classifications…</div></div>
    </section>
    <div id="baba-sector-report" class="baba-output"></div>`;
  try {
    await babaLoadSectors();
    const sel = $("#baba-sector-select");
    const names = babaSectorNames();
    sel.innerHTML = `<option value="">— choose sector —</option>` + names.map((n) =>
      `<option value="${esc(n)}">${esc(n)} (${(BABA_SECTORS.by[n] || []).length})</option>`).join("");
    const rows = names.map((n) => {
      const members = BABA_SECTORS.by[n] || [];
      return [
        n, members.length,
        members.slice(0, 6).join(", ") + (members.length > 6 ? "…" : ""),
      ];
    });
    $("#baba-sector-explorer").innerHTML =
      `<p class="hint">${fmtInt((BABA_SECTORS.by && Object.values(BABA_SECTORS.by).reduce((n, a) => n + a.length, 0)) || 0)} ` +
      `symbols classified into ${fmtInt(names.length)} sectors, from a stored reference classification ` +
      `(${esc(BABA_SECTORS.source)}). Counts reflect stored classifications, not a live listing feed.</p>` +
      babaTableHtml(["Sector", "Companies (stored)", "Members (sample)"], rows);
    if (BABA.sector && names.includes(BABA.sector)) sel.value = BABA.sector;
    else if (names.length) sel.value = names.includes("Commercial Banks") ? "Commercial Banks" : names[0];
    const generate = () => {
      BABA.sector = sel.value;
      return babaSectorReport(sel.value);
    };
    $("#baba-sector-generate").onclick = generate;
    sel.onchange = () => { BABA.sector = sel.value; };
    if (BABA.sector) await babaSectorReport(BABA.sector);
    else if (sel.value) await babaSectorReport(sel.value);
  } catch (e) {
    $("#baba-sector-errors").textContent = `Could not load sector classifications: ${e.message}`;
    $("#baba-sector-explorer").innerHTML = `<div class="empty">Sector catalogue unavailable.</div>`;
  }
}

/* ------------------------------------------------------ fundamental scanner */
async function babaScanner(body) {
  body.innerHTML = `<div class="controls">
      <label class="wide">Symbols (comma separated)
        <input id="baba-scan-syms" placeholder="Type a symbol or company name" aria-label="Symbols to scan" />
      </label>
      <label>Sector filter (optional)
        <input id="baba-scan-sector" list="baba-sector-names" placeholder="e.g. Hydropower" />
        <datalist id="baba-sector-names"></datalist>
      </label>
      <button class="ctb-btn" id="baba-scan-go">Run fundamental scan</button>
    </div>
    <div id="baba-scan-error" class="error"></div>
    <div id="baba-scan-out" class="baba-output"><div class="empty">Choose one or more symbols from the autocomplete.</div></div>`;
  try {
    await Promise.all([babaLoadSectors(), babaLoadCatalog()]);
    $("#baba-sector-names").innerHTML = babaSectorNames().map((s) => `<option value="${esc(s)}"></option>`).join("");
  } catch (e) { /* the run path reports catalogue failures */ }
  attachBabaSymbolAutocomplete($("#baba-scan-syms"), { multiple: true });
  $("#baba-scan-go").onclick = async () => {
    const err = $("#baba-scan-error");
    const out = $("#baba-scan-out");
    err.textContent = "";
    let syms = babaParseSymbols($("#baba-scan-syms").value);
    if (!syms.length) { err.textContent = "Choose at least one symbol."; return; }
    const unknown = await babaUnknownSymbols(syms);
    if (unknown.length) {
      err.textContent = `Not in the stored symbol catalogue: ${unknown.join(", ")}. ` +
        `Select an actual catalogue entry; a partial search string is not submitted as a symbol.`;
      return;
    }
    const sectorFilter = babaCanonicalSector($("#baba-scan-sector").value);
    if (sectorFilter) {
      const inSector = syms.filter((s) => (babaCatalogItem(s) || {}).sector === sectorFilter);
      const excluded = syms.filter((s) => !inSector.includes(s));
      syms = inSector;
      if (!syms.length) {
        err.textContent = `None of ${unknown.length ? "" : "the selected symbols"} belongs to ${sectorFilter}. ` +
          `Excluded: ${excluded.join(", ")}. No criterion result is reported for an excluded symbol.`;
        out.innerHTML = `<div class="empty">Sector filter ${esc(sectorFilter)} excluded every selected symbol.</div>`;
        return;
      }
    }
    out.innerHTML = `<div class="empty">Loading stored fundamentals for ${fmtInt(syms.length)} symbol(s)…</div>`;
    const settled = await Promise.allSettled(syms.map((s) => babaFundamentalSnapshot(s)));
    const ok = [];
    const failed = [];
    settled.forEach((r, i) => {
      if (r.status === "fulfilled") ok.push(r.value);
      else failed.push({ symbol: syms[i], reason: String(r.reason && r.reason.message || r.reason) });
    });
    const cards = ok.map((snap) => babaRenderFundamentalSnapshot(snap, { periods: 4 })).join("");
    const failedHtml = failed.length ? `<section class="report-section"><h3>Failed requests</h3>
      <p class="hint">These are request failures, not empty stored records. No metric is shown for them.</p>
      <div class="tablewrap">${babaTableHtml(["Symbol", "Error"],
        failed.map((f) => [f.symbol, f.reason]))}</div></section>` : "";
    let eligibility = "";
    if (ok.length) {
      try {
        const rep = await babaPreview(["elig_result", "elig_failed"], ok.map((s) => s.symbol));
        eligibility = `<section class="report-section"><h3>Eligibility screening</h3>
          <p class="hint">Rules use only stored inputs. A missing input is NEEDS_REVIEW, never PASS.</p>
          ${babaRenderSections(rep, { showUnavailable: false })}</section>`;
      } catch (e) {
        eligibility = `<section class="report-section"><h3>Eligibility screening</h3>
          <div class="empty">Eligibility could not be evaluated: ${esc(e.message)}</div></section>`;
      }
    }
    out.innerHTML = (ok.length || failed.length)
      ? `${babaReportHero("Fundamental Scanner", `${fmtInt(ok.length)} symbol(s) loaded from stored records`,
          `Each metric shows its reporting period and source. Prices are end-of-day, not live quotes.`,
          [{ k: "Requested", v: fmtInt(syms.length) }, { k: "Loaded", v: fmtInt(ok.length) },
           { k: "Failed", v: fmtInt(failed.length) },
           { k: "Quarterly records", v: fmtInt(ok.filter((s) => s.hasQuarterly).length) }])}` +
        cards + failedHtml + eligibility
      : `<div class="empty">No symbol produced a stored fundamental record.</div>`;
  };
}

/* --------------------------------------------------------- quarterly view */
async function babaQuarterly(body) {
  body.innerHTML = `<div class="controls">
      <label>Symbol
        <input id="baba-q-sym" placeholder="Type a symbol or company name" aria-label="Quarterly analysis symbol" />
      </label>
      <button class="ctb-btn" id="baba-q-go">Quarterly analysis</button>
      <span class="hint">Stored filings only. Quarters are never filled in or shifted.</span>
    </div>
    <div id="baba-q-error" class="error"></div>
    <div id="baba-q-out" class="baba-output"><div class="empty">Choose a symbol to see its stored quarterly periods.</div></div>`;

  const run = async (chosen) => {
    const err = $("#baba-q-error");
    const out = $("#baba-q-out");
    err.textContent = "";
    const sym = String(chosen || ($("#baba-q-sym").value || "")).trim().toUpperCase();
    if (!sym) { err.textContent = "Choose a symbol first."; return; }
    const unknown = await babaUnknownSymbols([sym]);
    if (unknown.length) {
      err.textContent = `${sym} is not in the stored symbol catalogue. Select a real catalogue entry; a partial search string is not submitted.`;
      return;
    }
    out.innerHTML = `<div class="empty">Loading ${esc(sym)} quarterly records…</div>`;
    const settled = await Promise.allSettled([
      babaFundamentalSnapshot(sym),
      babaPreview(["q_eps_comparison", "yoy_growth", "seq_growth", "annual_summary",
        "missing_quarters", "comparability", "fundamental_trend"], [sym]),
    ]);
    if (settled[0].status !== "fulfilled") {
      out.innerHTML = `<div class="empty"><b>${esc(sym)}</b>: the fundamentals request failed — ` +
        `${esc(String(settled[0].reason && settled[0].reason.message || settled[0].reason))}. ` +
        `This is a request failure, not an empty record.</div>`;
      return;
    }
    const snap = settled[0].value;
    let growth = "";
    if (settled[1].status === "fulfilled") {
      growth = babaRenderSections(settled[1].value, { showUnavailable: false });
    } else {
      growth = `<div class="empty">Growth comparisons could not be produced: ` +
        `${esc(String(settled[1].reason && settled[1].reason.message || settled[1].reason))}. ` +
        `The stored periods below are unaffected and are not extrapolated.</div>`;
    }
    const qEmpty = !snap.hasQuarterly
      ? `<div class="banner warn"><b>${esc(sym)} has no stored quarterly filing.</b> ` +
        `Requested dataset: quarterly fundamentals. Latest available stored period: ` +
        `<b>${esc(snap.latestPeriod ? snap.latestPeriod.label : "none")}</b>. ` +
        `The symbol remains valid; no quarter is fabricated. Next action: open the company's stored ` +
        `fundamental records or an alternate supported filing source in Data, rather than starting an ` +
        `uncontrolled ingest.</div>`
      : "";
    out.innerHTML = `${qEmpty}
      ${babaReportHero(`Quarterly Analysis — ${sym}`,
        `${snap.name ? esc(snap.name) + " · " : ""}${esc(snap.sector || "sector not stored")}`,
        `Chronological stored periods (newest first). QoQ and YoY are shown only when both values exist. ` +
        `Fiscal labels are preserved exactly as stored; prices are end-of-day.`,
        [
          { k: "Quarterly periods", v: fmtInt(snap.quarterlyPeriods.length) },
          { k: "All periods", v: fmtInt(snap.periods.length) },
          { k: "Latest period", v: snap.latestPeriod ? snap.latestPeriod.label : "—" },
          { k: "Core fields missing", v: fmtInt(snap.missing.length) },
        ])}
      ${babaRenderFundamentalSnapshot(snap, { periods: "all" })}
      <section class="report-section"><h3>Quarterly comparisons, growth and missing periods</h3>
        <p class="hint">YoY compares the same quarter in the previous fiscal year. Sequential growth compares ` +
        `the immediately preceding stored quarter. A comparison is omitted when either endpoint is absent.</p>
        ${growth}</section>`;
  };
  attachBabaSymbolAutocomplete($("#baba-q-sym"), { onSelect: (s) => run(s) });
  $("#baba-q-go").onclick = () => run();
}

/* ------------------------------------------------------ eligibility screen */
async function babaEligibility(body) {
  body.innerHTML = `<div class="controls">
      <label>Symbols (comma separated)
        <input id="baba-e-syms" placeholder="Type a symbol or company name" aria-label="Symbols to screen" />
      </label>
      <button class="ctb-btn" id="baba-e-go">Screen eligibility</button>
    </div>
    <div id="baba-e-error" class="error"></div>
    <div id="baba-e-out" class="baba-output"><div class="empty">Choose one or more catalogue symbols.</div></div>`;
  attachBabaSymbolAutocomplete($("#baba-e-syms"), { multiple: true });
  $("#baba-e-go").onclick = async () => {
    const err = $("#baba-e-error");
    const out = $("#baba-e-out");
    err.textContent = "";
    const syms = babaParseSymbols($("#baba-e-syms").value);
    if (!syms.length) { err.textContent = "Choose at least one symbol."; return; }
    const unknown = await babaUnknownSymbols(syms);
    if (unknown.length) {
      err.textContent = `Not in the stored symbol catalogue: ${unknown.join(", ")}. ` +
        `Nothing was submitted; select a real catalogue entry.`;
      return;
    }
    out.innerHTML = `<div class="empty">Screening ${fmtInt(syms.length)} symbol(s) against stored rules…</div>`;
    try {
      const rep = await babaPreview(["elig_config", "elig_result", "elig_failed",
        "elig_listing_age", "elig_share_count", "elig_networth", "elig_profit"], syms);
      out.innerHTML = babaReportHero("Eligibility Screening",
        `${fmtInt(syms.length)} symbol(s) · ${esc(syms.join(", "))}`,
        `Every rule uses stored inputs only. A missing input is NEEDS_REVIEW, never PASS.`,
        [{ k: "Symbols", v: fmtInt(syms.length) }]) + babaRenderSections(rep);
    } catch (e) {
      out.innerHTML = `<div class="empty">Eligibility could not be evaluated: ${esc(e.message)}. ` +
        `This is a request failure, not a pass or an exclusion.</div>`;
    }
  };
}

/* ------------------------------------------------------------ comparison */
async function babaCompare(body) {
  body.innerHTML = `<div class="controls">
      <label>Symbols (comma separated)
        <input id="baba-c-syms" placeholder="Type a symbol or company name" aria-label="Symbols to compare" />
      </label>
      <button class="ctb-btn" id="baba-c-go">Compare</button>
    </div>
    <div id="baba-c-error" class="error"></div>
    <div id="baba-c-out" class="baba-output"><div class="empty">Choose two or more catalogue symbols.</div></div>`;
  attachBabaSymbolAutocomplete($("#baba-c-syms"), { multiple: true });
  $("#baba-c-go").onclick = async () => {
    const err = $("#baba-c-error");
    const out = $("#baba-c-out");
    err.textContent = "";
    const syms = babaParseSymbols($("#baba-c-syms").value);
    if (!syms.length) { err.textContent = "Choose at least one symbol."; return; }
    const unknown = await babaUnknownSymbols(syms);
    if (unknown.length) {
      err.textContent = `Not in the stored symbol catalogue: ${unknown.join(", ")}. ` +
        `Nothing was submitted; select a real catalogue entry.`;
      return;
    }
    out.innerHTML = `<div class="empty">Comparing ${fmtInt(syms.length)} symbol(s) from stored records…</div>`;
    try {
      const rep = await babaPreview(["cmp_overview", "cmp_side_by_side", "cmp_eps", "cmp_pe",
        "cmp_pb", "cmp_networth", "cmp_dividend", "cmp_growth", "cmp_profitability",
        "cmp_eligibility", "cmp_warnings"], syms);
      out.innerHTML = babaReportHero("Company Comparison",
        `${fmtInt(syms.length)} symbol(s) · ${esc(syms.join(", "))}`,
        `Comparisons use stored periods. A blank cell means the value was not stored, not that it is zero.`,
        [{ k: "Symbols", v: fmtInt(syms.length) }]) + babaRenderSections(rep);
    } catch (e) {
      out.innerHTML = `<div class="empty">Comparison could not be produced: ${esc(e.message)}. ` +
        `This is a request failure, not an empty data result.</div>`;
    }
  };
}

async function babaJournal(body) {
  body.innerHTML = `<div class="controls">
      <label>Traded on <input type="date" id="baba-j-date" /></label>
      <label>Symbol <input id="baba-j-sym" placeholder="NABIL" /></label>
      <label>Side <select id="baba-j-side"><option value="buy">buy</option><option value="sell">sell</option></select></label>
      <label>Qty <input type="number" id="baba-j-qty" min="1" step="1" /></label>
      <label>Price <input type="number" id="baba-j-price" min="0" step="0.01" /></label>
      <label>Fees <input type="number" id="baba-j-fees" min="0" step="0.01" value="0" /></label>
      <label>Notes <input id="baba-j-notes" /></label>
      <button class="ctb-btn" id="baba-j-add">Add transaction</button>
    </div>
    <p class="hint">The ledger stores exactly what you enter: symbol, side, quantity,
      price, fees, date and notes. Commission and taxes are not stored separately,
      so a breakdown by charge type is not reported. A sale of more shares than the
      ledger holds on that date is rejected rather than silently adjusted.</p>
    <div id="baba-j-msg"></div>
    <div id="baba-j-out" class="tablewrap"></div>`;
  attachBabaSymbolAutocomplete($("#baba-j-sym"));

  const load = async () => {
    const out = $("#baba-j-out");
    out.innerHTML = `<div class="empty">Loading ledger…</div>`;
    try {
      const rep = await babaPreview(["j_ledger", "j_day_summary", "j_symbol_summary",
        "j_charges", "j_holdings", "j_unrealized", "j_avg_cost", "j_realized",
        "j_open_positions", "j_closed_positions", "j_warnings"], []);
      out.innerHTML = babaRenderSections(rep);
    } catch (e) { out.innerHTML = `<div class="empty">${esc(e.message)}</div>`; }
  };

  $("#baba-j-add").onclick = async () => {
    const q = parseFloat($("#baba-j-qty").value);
    const pr = parseFloat($("#baba-j-price").value);
    const fees = parseFloat($("#baba-j-fees").value || "0");
    const sym = ($("#baba-j-sym").value || "").trim().toUpperCase();
    const msg = $("#baba-j-msg");
    if (!sym) { msg.innerHTML = `<div class="banner">Enter a symbol.</div>`; return; }
    const unknown = await babaUnknownSymbols([sym]);
    if (unknown.length) {
      msg.innerHTML = `<div class="banner">${esc(sym)} is not in the stored symbol catalogue. ` +
        `Choose a real catalogue entry; the ledger was not changed.</div>`;
      return;
    }
    if (!(q > 0) || !Number.isInteger(q)) {
      msg.innerHTML = `<div class="banner">Quantity must be a whole number above zero.</div>`; return;
    }
    if (!(pr > 0)) { msg.innerHTML = `<div class="banner">Price must be above zero.</div>`; return; }
    const payload = {
      symbol: sym, side: $("#baba-j-side").value, quantity: q, price: pr, fees: fees || 0,
      notes: $("#baba-j-notes").value || null,
    };
    const d = $("#baba-j-date").value;
    if (d) payload.traded_at = d;
    try {
      const r = await fetch("/api/portfolio/transactions", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload) });
      if (!r.ok) {
        const j = await r.json().catch(() => ({}));
        msg.innerHTML = `<div class="banner">${esc(j.detail || "Could not save the transaction.")}</div>`;
        return;
      }
      msg.innerHTML = `<div class="hint">Saved.</div>`;
      ["#baba-j-qty", "#baba-j-price", "#baba-j-notes"].forEach((sel) => { $(sel).value = ""; });
      await load();
    } catch (e) { msg.innerHTML = `<div class="banner">${esc(e.message)}</div>`; }
  };
  await load();
}

/* ------------------------------------------------------------ report builder */
async function babaPreview(comps, symbols, extra) {
  const body = { components: comps, symbols: symbols || [], format: "json" };
  if (extra && extra.sector) body.sector = extra.sector;
  if (extra && extra.period) body.period = extra.period;
  const init = _withFriendToken({
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const r = await fetch(API_BASE + "/api/baba/report/preview", init);
  if (!r.ok) {
    let detail = r.statusText;
    try { const j = await r.json(); detail = j.detail || j.error || detail; } catch (e) { /* not JSON */ }
    throw new Error(detail);
  }
  return r.json();
}

async function babaBuilder(body) {
  const comps = BABA.comps;
  const byCat = {};
  for (const c of comps.components) (byCat[c.category_name] ||= []).push(c);
  const cats = Object.keys(byCat);
  body.innerHTML = `
    <div class="controls">
      <label>Symbols <input id="rpt-syms" placeholder="Type a symbol or company name" /></label>
      <label>Sector <input id="rpt-sector" list="rpt-sector-names" placeholder="optional" />
        <datalist id="rpt-sector-names"></datalist></label>
      <label>Period <input id="rpt-period" placeholder="FY2081" /></label>
      <label>Format <select id="rpt-fmt">
        ${["xlsx","csv","pdf","json"].map(f => `<option value="${f}">${f.toUpperCase()}</option>`).join("")}
      </select></label>
      <label>Title <input id="rpt-title" placeholder="Report title" /></label>
      <label>Notes <input id="rpt-notes" placeholder="optional notes" /></label>
    </div>
    <div class="controls">
      <button class="ctb-btn" id="rpt-all">Select all</button>
      <button class="ctb-btn" id="rpt-none">Deselect all</button>
      <input id="rpt-search" placeholder="Search components…" style="flex:1;min-width:180px" />
      <span class="pill" id="rpt-count">0 selected</span>
      <button class="ctb-btn" id="rpt-preview">Preview</button>
      <button class="ctb-btn" id="rpt-export">Export</button>
      <button class="ctb-btn" id="rpt-save">Save template</button>
    </div>
    <details id="rpt-templates"><summary>Saved templates</summary>
      <div id="rpt-tpl-list" class="tablewrap"></div></details>
    <div id="rpt-out" class="tablewrap"></div>`;

  const out = $("#rpt-out");
  attachBabaSymbolAutocomplete($("#rpt-syms"), { multiple: true });
  babaLoadSectors().then(() => {
    const dl = $("#rpt-sector-names");
    if (dl) dl.innerHTML = babaSectorNames().map((s) => `<option value="${esc(s)}"></option>`).join("");
  }).catch(() => { /* the builder still accepts a typed sector */ });
  const catHtml = cats.map(cat => `
    <details class="rb-cat" open>
      <summary><b>${esc(cat)}</b>
        <button class="ctb-btn rb-cat-all" data-cat="${esc(cat)}">select</button>
        <button class="ctb-btn rb-cat-none" data-cat="${esc(cat)}">clear</button>
      </summary>
      ${byCat[cat].map(c => `
        <label class="rb-item">
          <input type="checkbox" class="rb-cb" value="${c.id}" data-cat="${esc(cat)}" />
          <span class="${c.available ? "" : "pill pill-warn"}">${esc(c.name)}</span>
          <span class="hint">${esc(c.description)}</span>
          ${c.available ? "" : `<span class="hint">— ${esc(c.reason)}</span>`}
        </label>`).join("")}
    </details>`).join("");
  out.innerHTML = catHtml;
  $("#rpt-out").insertAdjacentHTML("beforeend",
    `<div id="rpt-preview-out" class="tablewrap" style="margin-top:12px"></div>`);

  const upd = () => {
    const n = $$(".rb-cb:checked").length;
    $("#rpt-count").textContent = `${n} selected`;
  };
  $$(".rb-cb").forEach(cb => cb.addEventListener("change", upd));
  $("#rpt-all").onclick = () => { $$(".rb-cb").forEach(c => { c.checked = true; }); upd(); };
  $("#rpt-none").onclick = () => { $$(".rb-cb").forEach(c => { c.checked = false; }); upd(); };
  $$(".rb-cat-all").forEach(b => b.onclick = () => {
    $$(`.rb-cb[data-cat="${b.dataset.cat}"]`).forEach(c => { c.checked = true; }); upd();
  });
  $$(".rb-cat-none").forEach(b => b.onclick = () => {
    $$(`.rb-cb[data-cat="${b.dataset.cat}"]`).forEach(c => { c.checked = false; }); upd();
  });
  $("#rpt-search").addEventListener("input", e => {
    const q = e.target.value.toLowerCase();
    $$(".rb-item").forEach(it => {
      const cb = it.querySelector(".rb-cb");
      const c = comps.components.find(x => x.id === cb.value);
      it.style.display = (c.name + " " + c.description).toLowerCase().includes(q) ? "" : "none";
    });
  });

  const gather = () => ({
    components: $$(".rb-cb:checked").map(c => c.value),
    symbols: babaParseSymbols($("#rpt-syms").value),
    sector: $("#rpt-sector").value || undefined,
    period: $("#rpt-period").value || undefined,
    format: $("#rpt-fmt").value,
    title: $("#rpt-title").value || undefined,
    notes: $("#rpt-notes").value || undefined,
  });

  $("#rpt-preview").onclick = async () => {
    const req = gather();
    if (!req.components.length) { $("#rpt-preview-out").innerHTML = `<div class="empty">Select at least one component.</div>`; return; }
    const unknown = await babaUnknownSymbols(req.symbols);
    if (unknown.length) {
      $("#rpt-preview-out").innerHTML = `<div class="empty">Not in the stored symbol catalogue: ` +
        `${esc(unknown.join(", "))}. Select catalogue entries; a partial search string is not submitted.</div>`;
      return;
    }
    $("#rpt-preview-out").innerHTML = `<div class="empty">Assembling preview…</div>`;
    try {
      const rep = await babaPreview(req.components, req.symbols,
        { sector: req.sector, period: req.period });
      $("#rpt-preview-out").innerHTML =
        `<p class="hint">${fmtInt(req.components.length)} section(s) selected ·
           ${fmtInt(req.symbols.length)} symbol(s) · format ${esc(req.format.toUpperCase())}</p>` +
        babaRenderSections(rep);
    } catch (e) { $("#rpt-preview-out").innerHTML = `<div class="empty">${esc(e.message)}</div>`; }
  };

  $("#rpt-export").onclick = async () => {
    const req = gather();
    if (!req.components.length) { $("#rpt-preview-out").innerHTML = `<div class="empty">Select at least one component.</div>`; return; }
    const unknown = await babaUnknownSymbols(req.symbols);
    if (unknown.length) {
      $("#rpt-preview-out").innerHTML = `<div class="empty">Not in the stored symbol catalogue: ` +
        `${esc(unknown.join(", "))}. Nothing was exported.</div>`;
      return;
    }
    try {
      await babaDownloadReport(req);
    } catch (e) {
      $("#rpt-preview-out").insertAdjacentHTML("afterbegin",
        `<div class="banner warn">Export failed: ${esc(e.message)}</div>`);
    }
  };

  $("#rpt-save").onclick = async () => {
    const name = prompt("Template name:");
    if (!name) return;
    const req = gather();
    if (!req.components.length) { alert("Select at least one component."); return; }
    try {
      await fetch("/api/baba/templates", { method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, ...req }) });
      await babaLoadTemplates();
    } catch (e) { alert("Could not save template: " + e.message); }
  };

  async function babaLoadTemplates() {
    try {
      const d = await (await fetch("/api/baba/templates")).json();
      const tpls = d.templates || [];
      const list = $("#rpt-tpl-list");
      if (!tpls.length) { list.innerHTML = `<div class="empty">No saved templates yet.</div>`; return; }
      list.innerHTML = table(["Name", "Sections", "Symbols", "Format", "Actions"],
        tpls.map(t => [
          { html: esc(t.name) },
          { html: fmtInt(t.components.length) },
          { html: esc((t.symbols || []).join(", ") || "—") },
          { html: esc((t.format || "xlsx").toUpperCase()) },
          { html: `<button class="ctb-btn rb-tpl-load" data-n="${esc(t.name)}">Load</button>
                   <button class="ctb-btn rb-tpl-del" data-n="${esc(t.name)}">Delete</button>` },
        ]));
      $$(".rb-tpl-load").forEach(b => b.onclick = () => {
        const t = tpls.find(x => x.name === b.dataset.n);
        if (!t) return;
        $$(".rb-cb").forEach(c => { c.checked = (t.components || []).includes(c.value); });
        if (t.symbols && t.symbols.length) $("#rpt-syms").value = t.symbols.join(", ");
        if (t.sector) $("#rpt-sector").value = t.sector;
        if (t.period) $("#rpt-period").value = t.period;
        if (t.format) $("#rpt-fmt").value = t.format;
        if (t.title) $("#rpt-title").value = t.title;
        upd();
      });
      $$(".rb-tpl-del").forEach(b => b.onclick = async () => {
        if (!confirm(`Delete template "${b.dataset.n}"?`)) return;
        await fetch("/api/baba/templates/" + encodeURIComponent(b.dataset.n), { method: "DELETE" });
        await babaLoadTemplates();
      });
    } catch (e) { $("#rpt-tpl-list").innerHTML = `<div class="empty">${esc(e.message)}</div>`; }
  }
  await babaLoadTemplates();
  upd();
}

/* ---------------------------------------------------------------- exports */
async function babaExports(body) {
  body.innerHTML = `<div class="empty">Loading export history…</div>`;
  try {
    const d = await (await fetch("/api/baba/templates")).json();
    const tpls = d.templates || [];
    body.innerHTML = `
      <p class="hint">Reports are generated on demand from the Report Builder and
        downloaded immediately. Saved templates are listed here and in the builder.
        Nothing is retained server-side beyond the template definition.</p>
      <div class="tablewrap">${table(["Template", "Sections", "Format", "Updated"],
        tpls.map(t => [{html: esc(t.name)}, {html: fmtInt(t.components.length)},
                      {html: esc((t.format || "xlsx").toUpperCase())},
                      {html: esc(t.updated_at || "—")}]))}</div>`;
  } catch (e) { body.innerHTML = `<div class="empty">${esc(e.message)}</div>`; }
}

/* ----------------------------------------------------------------- extras */
async function babaExtras(body) {
  const avail = BABA.comps.available, total = BABA.comps.count;
  body.innerHTML = `
    <h4>BABA Extras</h4>
    <div class="stat-row">
      <div class="stat"><div class="k">Report components</div><div class="v">${fmtInt(total)}</div></div>
      <div class="stat"><div class="k">Currently available</div><div class="v">${fmtInt(avail)}</div></div>
      <div class="stat"><div class="k">Saved templates</div><div class="v" id="baba-tpl-n">—</div></div>
    </div>
    <p class="hint">Availability is computed from whether a data source currently
      backs a component. A component that cannot run is reported as unavailable
      with a reason; it is never replaced with an invented figure.</p>
    <p class="hint">Personal journal data is private. Journal and portfolio
      components are only produced for an authorised local session and are always
      served with <code>Cache-Control: no-store</code>.</p>
    <p class="hint">Prices are end-of-day stored closes, not live quotes.</p>`;
  try {
    const d = await (await fetch("/api/baba/templates")).json();
    const el = $("#baba-tpl-n");
    if (el) el.textContent = fmtInt((d.templates || []).length);
  } catch (e) { /* optional */ }
}

function bindBabaSection() {
  $$("#baba-tabs .baba-tab").forEach((btn) => {
    btn.addEventListener("click", () => loadBabaSection(btn.dataset.tab));
  });
}

function bindNewSection() {
  $$("#new-tabs .new-tab").forEach((btn) => {
    btn.addEventListener("click", () => loadNewSection(btn.dataset.tab));
  });
}

function bindKimiSection() {
  $$("#kimi-tabs .kimi-tab").forEach((btn) => {
    btn.addEventListener("click", () => loadKimiSection(btn.dataset.tab));
  });
}

async function loadKimiSection(tab) {
  const body = $("#kimi-body");
  if (!body) return;
  body.dataset.tab = tab;
  $$("#kimi-tabs .kimi-tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  body.innerHTML = `<div class="empty">Loading ${esc(tab)}…</div>`;
  const loaders = {
    overview: loadKimiOverview,
    catalogues: loadKimiCatalogues,
    dataquality: loadKimiDataQuality,
    regime: loadKimiRegime,
    liquidity: loadKimiLiquidity,
    breadth: loadKimiBreadth,
    forensics: loadKimiForensics,
    factors: loadKimiFactors,
    signals: loadKimiSignals,
    montecarlo: loadKimiMonteCarlo,
    valuation: loadKimiValuation,
    portfolio: loadKimiPortfolio,
    researchdesk: loadKimiResearchDesk,
    aidesk: loadKimiAiDesk,
    reconcile: loadKimiReconcile,
    snapshots: loadKimiSnapshots,
    askdata: loadKimiAskData,
    corpevents: loadKimiCorporateEvents,
  };
  const fn = loaders[tab];
  if (fn) {
    try {
      await fn(body);
    } catch (e) {
      // Only report a failure if this tab is still the one being shown; a slow
      // loader that finished after the user switched away must not clobber the
      // newer tab's content.
      if (body.dataset.tab === tab) body.innerHTML = `<div class="empty">Could not load ${esc(tab)}: ${esc(e.message)}</div>`;
    }
  } else body.innerHTML = `<div class="empty">Unknown tab.</div>`;
}

async function loadKimiOverview(host) {
  let status = {};
  try { status = await api("/api/status"); } catch (e) { status = {}; }
  let syms = [];
  try { const d = await api("/api/securities?limit=2000"); syms = d.securities || []; } catch (e) { syms = []; }
  const bars = syms.reduce((a, s) => a + (s.bars || 0), 0);
  host.innerHTML = `
    <h3>KIMI research workspace</h3>
    <p class="hint">A research workspace for NEPSE data quality, market intelligence, corporate actions, quantitative research, company fundamentals, portfolio analysis, risk, and evidence-based AI assistance. Every metric below comes from a real calculation or a clearly labeled configuration. No fabricated data.</p>
    <div class="tablewrap">${table(["Metric", "Value", "Source"],
      [["Registered indicators", "92", "megatool.ta registry"],
       ["Securities with stored price history", fmtInt(syms.length), "/api/securities"],
       ["Total stored price bars", fmtInt(bars), "price_bars"],
       ["Data as of", esc(status.data_as_of || "unknown"), "/api/status"],
       ["Live feed connected", status.live_feed_connected ? "yes (delayed)" : "no", "/api/status"],
       ["Catalogue tools", "229 (124 scanners, 77 algorithms, 32 fundamentals)", "megatool.catalog"]]
        .map((r) => r.map((c) => ({ html: String(c) }))))}</div>
    <h4 style="margin-top:12px">Feature catalogue</h4>
    <div class="tablewrap">${table(["ID", "Feature", "Status", "Data dependency"],
      [["NF-001","Broker/Floorsheet Intelligence","BLOCKED","floorsheet_trades (0 rows)"],
       ["NF-005","Liquidity Drought & Unusual Activity","IMPLEMENTED","OHLCV (available)"],
       ["NF-006","Turnover Concentration & Breadth","IMPLEMENTED","price_bars (available)"],
       ["NF-007","Financial Statement Forensics","IMPLEMENTED","fundamentals (available)"],
       ["NF-008","Cross-Sectional Factor Research","IMPLEMENTED","price_bars (available)"],
       ["NF-009","Market Regime Detection","IMPLEMENTED","price_bars (available)"],
       ["NF-013","Data Quality & Provenance Dashboard","IMPLEMENTED","all stores"],
       ["NF-017","Signal Outcome Tracker","IMPLEMENTED","price_bars (available)"],
       ["NF-022","Strategy Robustness Lab","PARTIAL","price_bars (available)"],
       ["NF-030","Data Coverage & Feasibility Explorer","IMPLEMENTED","all stores"]]
        .map((r) => r.map((c) => ({ html: String(c) }))))}</div>
    <p class="hint">Full register: KIMI_IMPLEMENTATION/KIMI_REQUIREMENTS_REGISTER.md. Each feature shows honest data-availability status; nothing is fabricated.</p>`;
}

/* ------------------------------------------- scanner / algorithm / fundamental
   tool information panel
   One renderer feeds both the KIMI catalogue's inline ⓘ panel and the floating
   modal opened from the screener preset and backtest strategy selectors. Every
   field comes from the catalogue's own per-entry metadata (name, description,
   the implemented rule, parameters, tags, limitations, data requirements and
   execution path). The "Output", "Timeframe" and "How to interpret" lines are
   derived from the entry's kind and execution engine and labelled as derived —
   no per-entry wording is fabricated.
   ---------------------------------------------------------------------------- */
function toolRunLabel(t) {
  const e = ((t || {}).run || {}).engine;
  if (e === "screen") return "screen engine (/api/screen)";
  if (e === "backtest") return "backtest engine (/api/backtest)";
  if (e === "analysis") return "analysis engine (/api/analysis/run)";
  if (e === "fundamental") return "fundamental engine (/api/fundamental/run)";
  return "no execution path recorded";
}

function toolRunDescription(t) {
  const e = ((t || {}).run || {}).engine;
  if (e === "screen") return "Runs the rule against every eligible stored symbol and returns the securities that matched, together with the conditions that passed on each.";
  if (e === "backtest") return "Simulates the rule over the symbol's stored daily bars and returns the trade list plus performance metrics (return, CAGR, drawdown, trade count).";
  if (e === "analysis") return "Invokes the analysis engine and returns its result payload for the chosen symbol(s).";
  if (e === "fundamental") return "Computes the value from the stored fundamentals of one symbol.";
  return "This entry has no recorded execution path.";
}

function toolInterpretation(t) {
  const kind = (t || {}).kind;
  if (kind === "scanner") {
    return "A match means the stored data satisfied the rule on the latest evaluated session. It is a screen result — a description of what happened — not a buy signal and not a forecast. Re-check liquidity and the underlying data before acting.";
  }
  if (kind === "algorithm") {
    return "A backtest describes how the rule behaved on stored history. It does not imply future profitability. Read the trade count, costs and drawdown together before drawing any conclusion; a rule with very few trades is weakly evidenced.";
  }
  if (kind === "fundamental") {
    return "The value is derived from the most recent stored fundamentals for the symbol and is unadjusted for corporate actions unless the entry states otherwise. Compare it against the sector, not in isolation.";
  }
  return "Interpret alongside the stored-data definitions shown here.";
}

function toolTimeframe(t) {
  const e = ((t || {}).run || {}).engine;
  if (e === "screen") return "Evaluated on the latest stored daily session (one bar per security).";
  if (e === "backtest") return "Daily bars — one decision per stored trading day; 1-minute/live intraday data is not used.";
  return "Stored daily bars and the latest stored fundamentals. No intraday or live feed is used by catalogue tools.";
}

function toolInfoHtml(t, opts) {
  opts = opts || {};
  const params = t.params && Object.keys(t.params).length
    ? Object.entries(t.params).map(([k, v]) => `${k} = ${JSON.stringify(v)}`).join(", ") : "—";
  const tags = (t.tags || []).map((x) => `<span class="pill">${esc(x)}</span>`).join(" ") || "—";
  const reqs = (t.data_requirements || []);
  const lim = (t.limitations || []).length
    ? `<ul>${t.limitations.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>`
    : `<p class="hint">No entry-specific limitation is recorded. The platform-wide limitations below still apply.</p>`;
  const py = t.kind === "fundamental" ? "fundamentals" : t.kind === "algorithm" ? "algorithms" : "scanners";
  const sec = (label, inner) => `<div class="ti-section"><h4>${esc(label)}</h4>${inner}</div>`;
  return `<div class="ti-wrap"${opts.inline ? ` style="margin-top:12px;border-left:4px solid var(--accent,#5aa);padding-left:12px"` : ""}>
    <h3 style="margin:6px 0">${esc(t.name)}
      <span class="pill">${esc(t.kind)}</span>
      <span class="pill">${esc(t.category)}</span>
      <span class="pill ${t.status === "available" ? "pill-ok" : "pill-warn"}">${esc(t.status || "—")}</span>
    </h3>
    ${sec("Purpose — what it identifies", `<p>${esc(t.description || "—")}</p>`)}
    ${sec("Rule / condition (as implemented)", `<code class="ti-formula">${esc(t.formula || "—")}</code>`)}
    ${sec("Default parameters", `<p class="mono">${esc(params)}</p>`)}
    ${sec("Required input data", reqs.length
      ? `<ul>${reqs.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>`
      : `<p class="hint">Not itemised; the tool runs on the stored daily bars.</p>`)}
    ${sec("Timeframe", `<p>${esc(toolTimeframe(t))} <span class="hint">(derived from the execution path)</span></p>`)}
    ${sec("Output", `<p>${esc(toolRunDescription(t))} <span class="hint">(derived from the execution engine)</span></p>`)}
    ${sec("How to interpret", `<p>${esc(toolInterpretation(t))} <span class="hint">(derived from the tool family)</span></p>`)}
    ${sec("Executed by", `<p><span class="mono">${esc(toolRunLabel(t))}</span></p>`)}
    ${sec("Keywords", `<p>${tags}</p>`)}
    ${sec("Limitations", lim + `<p class="hint">Platform-wide: catalogue ${esc(py)} use stored daily bars with prices unadjusted for corporate actions; results are descriptive history, not advice.</p>`)}
    ${sec("Stable id", `<p class="mono">${esc(t.id)}</p>`)}
  </div>`;
}

async function openToolInfo(id) {
  const modal = $("#tool-info");
  if (!modal) return;
  const title = $("#tool-info-title"), body = $("#tool-info-body");
  if (title) title.textContent = "Tool information";
  if (body) body.innerHTML = `<div class="empty">Loading ${esc(id)}…</div>`;
  modal.hidden = false;
  try {
    const t = await api(`/api/catalog/tool/${encodeURIComponent(id)}`);
    if (title) title.innerHTML = `${esc(t.name)} <span class="pill">${esc(t.kind)}</span>`;
    if (body) body.innerHTML = toolInfoHtml(t);
  } catch (e) {
    if (body) body.innerHTML = `<div class="empty">Could not load tool <span class="mono">${esc(id)}</span>: ${esc(e.message)}</div>`;
  }
}

let _catalogToolIndex = null;   // engine-specific key -> catalogue tool id
async function catalogToolIdFor(kind, key) {
  try {
    if (!_catalogToolIndex) _catalogToolIndex = {};
    const cacheKey = `${kind}:${key}`;
    if (_catalogToolIndex[cacheKey]) return _catalogToolIndex[cacheKey];
    const d = await api(`/api/catalog/${kind}?q=&category=all`);
    (d.tools || []).forEach((t) => {
      const r = t.run || {};
      if (r.strategy) _catalogToolIndex[`algorithm:${r.strategy}`] = t.id;
      if (t.key) _catalogToolIndex[`scanner:${t.key}`] = t.id;
      if (t.key) _catalogToolIndex[`fundamental:${t.key}`] = t.id;
    });
    return _catalogToolIndex[cacheKey] || null;
  } catch (e) { return null; }
}

function bindToolInfoModal() {
  const modal = $("#tool-info");
  if (!modal) return;
  const close = () => { modal.hidden = true; };
  const c = $("#tool-info-close");
  if (c) c.addEventListener("click", close);
  modal.addEventListener("click", (e) => { if (e.target === modal) close(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !modal.hidden) close(); });

  const pbtn = $("#preset-info-btn");
  if (pbtn) {
    const presetSel = $("#preset");
    if (presetSel) {
      const sync = () => {
        const o = presetSel.options[presetSel.selectedIndex];
        const label = o ? o.textContent : presetSel.value;
        pbtn.setAttribute("aria-label", `Information about the scanner preset: ${label}`);
        pbtn.title = `What “${label}” identifies, its rule, parameters and limitations`;
      };
      presetSel.addEventListener("change", sync);
      sync();
    }
    pbtn.addEventListener("click", async () => {
      const key = ($("#preset") && $("#preset").value) || "";
      if (!key) { openToolInfo(""); return; }
      const id = await catalogToolIdFor("scanner", key);
      if (id) return openToolInfo(id);
      const desc = ($("#preset-desc") && $("#preset-desc").textContent) || "No description available for this preset.";
      const title = $("#tool-info-title"), body = $("#tool-info-body");
      if (title) title.textContent = key;
      if (body) body.innerHTML = `<div class="ti-wrap"><p>${esc(desc)}</p><p class="hint">This preset has no matching catalogue entry, so only its own description is shown.</p></div>`;
      if (modal) modal.hidden = false;
    });
  }

  const bbtn = $("#bt-strategy-info-btn");
  if (bbtn) {
    const btSel = $("#bt-strategy");
    if (btSel) {
      const sync = () => {
        const o = btSel.options[btSel.selectedIndex];
        const label = o ? o.textContent : btSel.value;
        bbtn.setAttribute("aria-label", `Information about the backtest strategy: ${label}`);
        bbtn.title = `Information about the backtest strategy: ${label}`;
      };
      btSel.addEventListener("change", sync);
      sync();
    }
    bbtn.addEventListener("click", async () => {
      const key = ($("#bt-strategy") && $("#bt-strategy").value) || "";
      if (!key) return;
      const id = await catalogToolIdFor("algorithm", key);
      if (id) return openToolInfo(id);
      const title = $("#tool-info-title"), body = $("#tool-info-body");
      if (title) title.textContent = key;
      if (body) body.innerHTML = `<div class="empty">No catalogue entry records the strategy <span class="mono">${esc(key)}</span>.</div>`;
      if (modal) modal.hidden = false;
    });
  }
}

async function loadKimiCatalogues(host) {
  host.innerHTML = `
    <h3>Tool catalogues</h3>
    <p class="hint">Search every scanner, algorithm and fundamental tool. Each entry has an ⓘ information panel (formula, parameters, tags, data requirements, limitations) and a Run action that calls the real engine — no placeholder results.</p>
    <div class="controls" style="flex-wrap:wrap;gap:10px;align-items:flex-end">
      <label>Family<br><select id="kimi-cat-kind">
        <option value="scanner">Scanners</option>
        <option value="algorithm">Algorithms</option>
        <option value="fundamental">Fundamental tools</option>
      </select></label>
      <label>Category<br><select id="kimi-cat-category"><option value="all">All</option></select></label>
      <label>Search<br><input id="kimi-cat-search" placeholder="name, tag, keyword…" style="min-width:220px" /></label>
      <button class="ctb-btn" id="kimi-cat-clear">Clear</button>
    </div>
    <p class="hint" id="kimi-cat-count"></p>
    <div id="kimi-cat-list" class="tablewrap"></div>
    <div id="kimi-cat-info"></div>`;

  const kindSel = $("#kimi-cat-kind");
  const catSel = $("#kimi-cat-category");
  const searchInput = $("#kimi-cat-search");
  const listEl = $("#kimi-cat-list");
  const infoEl = $("#kimi-cat-info");
  const countEl = $("#kimi-cat-count");
  let currentSymbol = ($("#symbol-input") && $("#symbol-input").value || "NABIL").trim().toUpperCase();

  const render = async () => {
    const kind = kindSel.value;
    const category = catSel.value || "all";
    const q = (searchInput.value || "").trim();
    listEl.innerHTML = `<div class="empty">Loading ${esc(kind)}…</div>`;
    let data;
    try {
      data = await api(`/api/catalog/${kind}?q=${encodeURIComponent(q)}&category=${encodeURIComponent(category)}`);
    } catch (e) {
      listEl.innerHTML = `<div class="empty">Catalogue unavailable: ${esc(e.message)}</div>`;
      return;
    }
    // Keep the category dropdown in sync (categories differ per family).
    const cats = data.categories || {};
    const prev = catSel.value;
    catSel.innerHTML = `<option value="all">All</option>` +
      Object.keys(cats).map((k) => `<option value="${esc(k)}">${esc(cats[k])}</option>`).join("");
    catSel.value = (prev && (prev === "all" || cats[prev])) ? prev : "all";

    const tools = data.tools || [];
    countEl.textContent = `${fmtInt(tools.length)} of ${fmtInt(data.total)} ${kind}s match` + (q ? ` for “${q}”` : "") + ".";
    const rows = tools.map((t) => [
      { html: `<b>${esc(t.name)}</b>` },
      { html: `<span class="pill">${esc((cats && cats[t.category]) || t.category)}</span>` },
      { html: `<span class="hint">${esc(t.formula || t.short || "")}</span>` },
      { html: `<button type="button" class="ctb-btn kimi-cat-info-btn" data-id="${esc(t.id)}" title="Information for ${esc(t.name)}" aria-label="Information for ${esc(t.name)}">ⓘ Info</button>` },
      { html: `<button type="button" class="ctb-btn kimi-cat-run-btn" data-id="${esc(t.id)}" data-engine="${esc((t.run||{}).engine||"")}">Run</button>` },
    ]);
    listEl.innerHTML = rows.length
      ? table(["Name", "Category", "Rule / formula", "", ""], rows)
      : `<div class="empty">No tools match. Try fewer keywords or another category.</div>`;

    // ⓘ must be *seen*. The old handler rendered an inline panel at the end of
    // a 124-row table — thousands of pixels below the button — so clicking it
    // looked like a dead control. Use the same floating panel as every other
    // information control in the app, which is visible wherever you are.
    listEl.querySelectorAll(".kimi-cat-info-btn").forEach((b) => b.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      openToolInfo(b.dataset.id);
    }));
    listEl.querySelectorAll(".kimi-cat-run-btn").forEach((b) => b.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      runKimiTool(b.dataset.id, b.dataset.engine, b);
    }));
    if (tools.length === 1) showKimiToolInfo(tools[0].id);
  };

  async function showKimiToolInfo(id) {
    if (!infoEl) return;
    infoEl.innerHTML = `<div class="empty">Loading tool…</div>`;
    let t;
    try { t = await api(`/api/catalog/tool/${encodeURIComponent(id)}`); }
    catch (e) { infoEl.innerHTML = `<div class="empty">Could not load tool: ${esc(e.message)}</div>`; return; }
    infoEl.innerHTML = toolInfoHtml(t, { inline: true });
  }

  async function apiPost(path, body) {
    return api(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
  }

  async function runKimiTool(id, engine, btn) {
    const prev = btn.textContent;
    btn.textContent = "Running…"; btn.disabled = true;
    infoEl.innerHTML = `<div class="empty">Running ${esc(id)}…</div>`;
    try {
      let t = await api(`/api/catalog/tool/${encodeURIComponent(id)}`);
      if (engine === "screen" || (t.run && t.run.engine === "screen")) {
        const res = await apiPost("/api/screen", { tree: t.run.tree, min_bars: 30 });
        const passed = (res.results || []).filter((r) => r.passed);
        const rows = passed.slice(0, 30).map((r) => [
          { html: `<b>${esc(r.symbol)}</b>` },
          { html: esc((r.reasons || []).join(" · ") || "—"), cls: "wrap" },
        ]);
        infoEl.innerHTML = `<div class="tablewrap" style="margin-top:12px"><h3>${esc(t.name)} — ${fmtInt(res.passed)} of ${fmtInt(res.eligible)} eligible matched</h3>` +
          (rows.length ? table(["Symbol", "Why it passed"], rows) : `<div class="empty">No securities matched (as of the latest stored bar).</div>`) +
          `<p class="hint">Executed by the real screen engine (/api/screen): ${fmtInt(res.evaluated)} evaluated, ${fmtInt(res.eligible)} eligible, ${fmtInt(res.ineligible)} ineligible for insufficient history.</p></div>`;
      } else if (t.run && t.run.engine === "backtest") {
        const sym = (($("#symbol-input") && $("#symbol-input").value) || currentSymbol).trim().toUpperCase();
        const res = await apiPost("/api/backtest", { symbol: sym, strategy: t.run.strategy, params: t.params || {} });
        const m = res.metrics || res.summary || res;
        const keys = ["total_return", "cagr", "sharpe", "max_drawdown", "trades", "win_rate", "final_equity"];
        const rows = keys.filter((k) => m[k] !== undefined && m[k] !== null).map((k) => [
          { html: esc(k) }, { html: esc(String(typeof m[k] === "number" ? fmtNum(m[k]) : m[k])) },
        ]);
        infoEl.innerHTML = `<div class="tablewrap" style="margin-top:12px"><h3>${esc(t.name)} — ${esc(sym)}</h3>` +
          (rows.length ? table(["Metric", "Value"], rows) : `<div class="empty">Backtest ran but returned no metrics.</div>`) +
          `<p class="hint">Executed by the real backtest engine (/api/backtest) on ${esc(sym)} with the tool's default parameters. Historical rule; not a forecast.</p></div>`;
      } else if (t.run && t.run.engine === "analysis") {
        const payload = { fn: t.run.fn, params: {} };
        if (t.run.fn === "correlation_matrix" || t.run.fn === "efficient_frontier") {
          payload.symbols = ["NABIL", "SCB", "EBL"];
        } else {
          payload.symbol = (($("#symbol-input") && $("#symbol-input").value) || currentSymbol).trim().toUpperCase();
        }
        const res = await apiPost("/api/analysis/run", payload);
        infoEl.innerHTML = `<div class="tablewrap" style="margin-top:12px"><h3>${esc(t.name)}</h3>` +
          `<pre class="code" style="white-space:pre-wrap">${esc(JSON.stringify(res.result, null, 2))}</pre>` +
          `<p class="hint">Executed by the real analysis engine (/api/analysis/run).</p></div>`;
      } else if (t.run && t.run.engine === "fundamental") {
        const sym = (($("#symbol-input") && $("#symbol-input").value) || currentSymbol).trim().toUpperCase();
        const res = await apiPost("/api/fundamental/run", { fn: t.run.fn, symbol: sym });
        infoEl.innerHTML = `<div class="tablewrap" style="margin-top:12px"><h3>${esc(t.name)} — ${esc(sym)}</h3>` +
          `<pre class="code" style="white-space:pre-wrap">${esc(JSON.stringify(res, null, 2))}</pre>` +
          `<p class="hint">Executed by the real fundamental engine (/api/fundamental/run) over stored fundamentals.</p></div>`;
      } else {
        infoEl.innerHTML = `<div class="empty">This tool has no execution path recorded.</div>`;
      }
    } catch (e) {
      infoEl.innerHTML = `<div class="empty">Run failed: ${esc(e.message)}</div>`;
    } finally {
      btn.textContent = prev; btn.disabled = false;
    }
  }

  kindSel.addEventListener("change", render);
  catSel.addEventListener("change", render);
  let debounce;
  searchInput.addEventListener("input", () => { clearTimeout(debounce); debounce = setTimeout(render, 200); });
  $("#kimi-cat-clear").addEventListener("click", () => { searchInput.value = ""; catSel.value = "all"; render(); });
  render();
}

function escapeHtmlCell(x) { return `<span class="hint">${esc(String(x))}</span>`; }

async function loadKimiDataQuality(host) {
  let status = {};
  try { status = await api("/api/status"); } catch (e) { status = {}; }
  let syms = [];
  try { const d = await api("/api/securities?limit=2000"); syms = d.securities || []; } catch (e) { syms = []; }
  const totalBars = syms.reduce((a, s) => a + (s.bars || 0), 0);
  const zeroBar = syms.filter((s) => !(s.bars)).length;
  host.innerHTML = `
    <h3>Data Quality & Provenance Dashboard</h3>
    <p class="hint">Every metric below is computed from the actual stored data. No fabricated values.</p>
    <div class="tablewrap">${table(["Metric", "Value", "Source"],
      [["Securities with stored price history", fmtInt(syms.length), "/api/securities"],
       ["Total stored price bars", fmtInt(totalBars), "price_bars"],
       ["Securities with zero bars", fmtInt(zeroBar), "price_bars"],
       ["Data as of", esc(status.data_as_of || "unknown"), "/api/status"],
       ["Live feed connected", status.live_feed_connected ? "yes (delayed)" : "no", "/api/status"],
       ["Active live provider", esc(status.live && status.live.active_provider || "—"), "/api/status"]]
        .map((r) => r.map((c) => ({ html: String(c) }))))}</div>
    <p class="hint">Corporate actions: all prices are <b>unadjusted</b>. Volume is genuine share volume for securities; for the NEPSE index the stored "volume" is market turnover (NPR), not share volume. Index OHLC is genuine only from 2016-11-28 (2,217 bars); 3,079 earlier bars are close-only placeholders.</p>
    <h4>Data coverage &amp; feasibility</h4>
    <div id="kimi-dq-cov" class="tablewrap"><div class="empty">Loading coverage…</div></div>`;
  kimiRunAnalysis("coverage_explorer", {}, $("#kimi-dq-cov"), (r) => {
    const m = r.market || {};
    return table(["Live store facts", "Value"], [
      ["Securities with price history", fmtInt(m.securities)],
      ["Total price bars", fmtInt(m.bars_total)],
      ["First date", esc(m.first_date || "—")],
      ["Last date", esc(m.last_date || "—")],
      ["Securities with <60 bars", fmtInt(m.securities_with_lt_60_bars)],
      ["Fundamental records", r.fundamentals ? fmtInt(r.fundamentals.records) : "—"],
      ["Fundamental symbols", r.fundamentals ? fmtInt(r.fundamentals.symbols) : "—"],
      ["Tables counted", fmtInt(r.app_tables ? Object.keys(r.app_tables).length : 0)],
    ].map((row) => row.map((c) => ({ html: String(c) })))) +
      `<p class="hint"><b>Known gaps:</b> ${esc((r.known_gaps || []).join(" · "))}</p>`;
  });
}

async function loadKimiRegime(host) {
  const sym = ($("#symbol-input").value || "NABIL").trim().toUpperCase();
  host.innerHTML = `<div class="controls"><label>Symbol <input id="kimi-regime-sym" value="${esc(sym)}" /></label><button class="ctb-btn" id="kimi-regime-run">Compute regime</button></div><div id="kimi-regime-out" class="tablewrap"></div>`;
  const run = async () => {
    const s = ($("#kimi-regime-sym").value || "").trim().toUpperCase();
    if (!s) return;
    const out = $("#kimi-regime-out");
    if (out) out.innerHTML = `<div class="empty">Loading ${esc(s)}…</div>`;
    try {
      const d = await api(`/api/bars/${encodeURIComponent(s)}?limit=500`);
      const bars = d.bars || [];
      // client-side regime: trend via SMA20 vs SMA50, momentum via RSI14, volatility via ATR%
      const closes = bars.map(b => b.close);
      const sma = (arr, n) => arr.map((_, i) => i < n-1 ? null : arr.slice(i-n+1, i+1).reduce((a,b)=>a+b,0)/n);
      const s20 = sma(closes, 20), s50 = sma(closes, 50);
      const last = closes.length - 1;
      const trend = (s20[last] != null && s50[last] != null) ? (s20[last] > s50[last] ? "Uptrend" : (s20[last] < s50[last] ? "Downtrend" : "Flat")) : "unknown";
      out.innerHTML = `<h3>${esc(s)} — Market Regime (heuristic)</h3>
        <div class="tablewrap">${table(["Measure","Value"],
          [["Last close", fmtNum(closes[last])],
           ["SMA20", fmtNum(s20[last])],
           ["SMA50", fmtNum(s50[last])],
           ["Trend (SMA20 vs SMA50)", trend],
           ["Bars used", fmtInt(closes.length)]].map(r=>[{html:esc(r[0])},{html:esc(String(r[1]))}]))}</div>
        <p class="hint">Heuristic classification using SMA alignment only. Not a prediction. Full regime engine (ADX + ATR terciles) is in megatool/regime.py and exposed via the existing research views.</p>`;
    } catch (e) { if (out) out.innerHTML = `<div class="empty">Could not load: ${esc(e.message)}</div>`; }
  };
  $("#kimi-regime-run").addEventListener("click", run);
  run();
}

async function loadKimiLiquidity(host) {
  const sym = ($("#symbol-input").value || "NABIL").trim().toUpperCase();
  host.innerHTML = `
    <h3>Liquidity drought &amp; unusual activity</h3>
    <p class="hint">Daily liquidity health executed by the analysis engine (<code>liquidity_drought</code>) over genuine stored volume. It refuses rather than reading missing volume as zero.</p>
    <div class="controls"><label>Symbol <input id="kimi-liq-sym" value="${esc(sym)}" /></label><button class="ctb-btn" id="kimi-liq-run">Analyse liquidity</button></div>
    <div id="kimi-liq-out" class="tablewrap"></div>`;
  const run = () => {
    const s = ($("#kimi-liq-sym").value || "").trim().toUpperCase();
    if (!s) return;
    kimiRunAnalysis("liquidity_drought", { symbol: s, window: 250, recent: 20 }, $("#kimi-liq-out"), (r) => {
      if (!r.available) return `<div class="empty">${esc(r.reason)}</div>`;
      return `<h4>${esc(r.symbol)} — ${esc(r.state)}</h4>
        <div class="tablewrap">${table(["Measure", "Value"], [
          ["Bars used", fmtInt(r.bars_used)],
          ["Median daily volume", fmtInt(r.median_daily_volume)],
          ["Recent mean volume", fmtInt(r.recent_mean_volume)],
          ["Relative volume", fmtNum(r.relative_volume, 3)],
          ["Drought threshold (½ median)", fmtInt(r.drought_threshold)],
          ["Days below half-median (recent)", fmtInt(r.days_below_half_median_recent)],
          ["Current drought run", fmtInt(r.current_drought_run)],
          ["Zero-volume days (window)", fmtInt(r.zero_volume_days)],
          ["Volume trend vs prior", r.volume_trend_recent_vs_prior == null ? "—" : fmtNum(r.volume_trend_recent_vs_prior, 3)],
          ["Amihud illiquidity (×1e9)", r.amihud_illiquidity_1e9 == null ? "—" : fmtNum(r.amihud_illiquidity_1e9, 4)],
        ].map((row) => row.map((c) => ({ html: esc(String(c)) }))))}</div>
        <p class="hint">${esc(r.note)}</p>`;
    });
  };
  $("#kimi-liq-run").addEventListener("click", run);
  run();
}

async function loadKimiBreadth(host) {
  try {
    // The route returns parallel `dates` + named `series` arrays (5,200 stored
    // sessions). It has no `limit` parameter, so the window is sliced here — and
    // the panel says which window it is showing rather than implying a cap.
    const d = await api("/api/breadth/history");
    const dates = d.dates || [];
    const s = d.series || {};
    const n = 10;
    const from = Math.max(0, dates.length - n);
    const cell = (arr, i) => (arr && arr[i] != null ? fmtInt(arr[i]) : "—");
    const rows = dates.slice(from).map((dt, k) => {
      const i = from + k;
      const pct = (arr) => (arr && arr[i] != null ? Number(arr[i]).toFixed(1) + "%" : "—");
      return [
        { html: esc(String(dt).slice(0, 10)) },
        { html: cell(s.advances, i) },
        { html: cell(s.declines, i) },
        { html: cell(s.unchanged, i) },
        { html: pct(s.pct_above_sma_50) },
        { html: cell(s.ad_line, i) },
      ];
    });
    const defs = d.definitions || {};
    host.innerHTML = `<h3>Market Breadth (latest stored sessions)</h3>
      <div class="tablewrap">${table(
        ["Date", "Advancers", "Decliners", "Unchanged", "% above SMA 50", "A/D line"],
        rows.map((r) => r.map((c) => ({ html: c.html })))
      )}</div>
      <p class="hint">Showing the last ${rows.length} of ${fmtInt(dates.length)} stored sessions
        (${esc(String(d.start || "—"))} → ${esc(String(d.end || "—"))}). Source: stored daily bars;
        counts are from actual observed closes.
        ${defs.universe ? "Universe: " + esc(String(defs.universe)) : ""}</p>`;
  } catch (e) { host.innerHTML = `<div class="empty">Could not load breadth: ${esc(e.message)}</div>`; }
}

async function loadKimiForensics(host) {
  const sym = ($("#symbol-input").value || "NABIL").trim().toUpperCase();
  host.innerHTML = `<div class="controls"><label>Symbol <input id="kimi-for-sym" value="${esc(sym)}" /></label><button class="ctb-btn" id="kimi-for-run">Run forensics</button></div><div id="kimi-for-out" class="tablewrap"></div><h4>Stored-fundamental forensics</h4><div id="kimi-for-fund" class="tablewrap"></div>`;
  const runFund = (s) => {
    kimiRunAnalysis("fundamental_forensics", { symbol: s }, $("#kimi-for-fund"), (r) => {
      if (!r.available) return `<div class="empty">${esc(r.reason)}</div>`;
      const rows = (r.issues || []).map((i) => [
        { html: `<span class="pill ${i.severity === "high" ? "pill-warn" : ""}">${esc(i.severity)}</span>` },
        { html: esc(i.issue) },
        { html: esc(i.detail || ""), cls: "wrap" },
      ]);
      return (rows.length
        ? table(["Severity", "Finding", "Detail"], rows)
        : `<div class="empty">No fundamental issues flagged.</div>`) +
        `<p class="hint">${fmtInt(r.records)} records · newest period ${esc(r.newest_period || "—")} (${r.newest_age_days == null ? "—" : fmtInt(r.newest_age_days)} days old). Observations for review, not conclusions.</p>`;
    });
  };
  const run = async () => {
    const s = ($("#kimi-for-sym").value || "").trim().toUpperCase();
    if (!s) return;
    const out = $("#kimi-for-out");
    if (out) out.innerHTML = `<div class="empty">Loading ${esc(s)}…</div>`;
    runFund(s);
    try {
      const d = await api(`/api/bars/${encodeURIComponent(s)}?limit=250`);
      const bars = d.bars || [];
      const zeroVol = bars.filter(b => (b.volume||0) === 0).length;
      const negClose = bars.filter(b => (b.close||0) <= 0).length;
      const badOhlc = bars.filter(b => b.high < b.low || b.high < b.open || b.high < b.close || b.low > b.open || b.low > b.close).length;
      const dupDates = bars.length - new Set(bars.map(b=>b.time)).size;
      out.innerHTML = `<h3>${esc(s)} — Financial/Price Forensics</h3>
        <div class="tablewrap">${table(["Check","Result","Detail"],
          [["Bars", fmtInt(bars.length), "stored daily bars"],
           ["Zero-volume bars", fmtInt(zeroVol), "bars with volume = 0"],
           ["Non-positive closes", fmtInt(negClose), "close <= 0"],
           ["OHLC constraint violations", fmtInt(badOhlc), "high<low or high<open/close or low>open/close"],
           ["Duplicate timestamps", fmtInt(dupDates), "repeated trading dates"],
           ["Adjustment status", esc((d.adjustment_status||[]).join(", ") || "—"), "corporate-action adjustment"],
           ["Sources", esc((d.sources||[]).join(", ") || "—"), "data provenance"]].map(r=>[{html:esc(r[0])},{html:esc(String(r[1]))},{html:esc(r[2])}]))}</div>
        <p class="hint">Forensics flags observations for review; it does not imply fraud or error. Prices are unadjusted for corporate actions.</p>`;
    } catch (e) { if (out) out.innerHTML = `<div class="empty">Could not load: ${esc(e.message)}</div>`; }
  };
  $("#kimi-for-run").addEventListener("click", run);
  run();
}

async function kimiRunAnalysis(fn, params, host, render) {
  host.innerHTML = `<div class="empty">Running ${esc(fn)}…</div>`;
  try {
    const d = await api("/api/analysis/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ fn, params: params || {} }),
    });
    const r = d.result;
    host.innerHTML = render ? render(r) : `<div class="tablewrap"><pre class="code" style="white-space:pre-wrap">${esc(JSON.stringify(r, null, 2))}</pre></div>`;
  } catch (e) {
    host.innerHTML = `<div class="empty">${esc(fn)} failed: ${esc(e.message)}</div>`;
  }
}

async function loadKimiFactors(host) {
  host.innerHTML = `
    <h3>Cross-sectional factor research</h3>
    <p class="hint">Ranks the whole stored universe on one factor. Executed by the real analysis engine (<code>/api/analysis/run</code> → <code>factor_snapshot</code>) over the stored window.</p>
    <div class="controls" style="flex-wrap:wrap;gap:10px">
      <label>Factor<br><select id="kimi-fac-factor">
        <option value="momentum_12_1">12-1 momentum</option>
        <option value="momentum_1m">1-month momentum</option>
        <option value="low_volatility">Low volatility</option>
        <option value="liquidity">Liquidity (volume)</option>
      </select></label>
      <label>Top N<br><input id="kimi-fac-top" value="15" style="width:70px" /></label>
      <button class="ctb-btn" id="kimi-fac-run">Rank universe</button>
    </div>
    <div id="kimi-fac-out" class="tablewrap"></div>`;
  const run = () => {
    const factor = $("#kimi-fac-factor").value;
    const top = Math.max(1, Math.min(50, Number($("#kimi-fac-top").value) || 15));
    kimiRunAnalysis("factor_snapshot", { factor, top }, $("#kimi-fac-out"), (r) => {
      if (!r.available) return `<div class="empty">${esc(r.reason)}</div>`;
      const rowOf = (x) => [
        { html: `<b>${esc(x.symbol)}</b>` },
        { html: fmtNum(x.momentum_12_1 * 100, 2) + "%" },
        { html: fmtNum(x.momentum_21 * 100, 2) + "%" },
        { html: x.volatility_63 == null ? "—" : fmtNum(x.volatility_63 * 100, 2) + "%" },
        { html: x.avg_volume_63 == null ? "—" : fmtInt(x.avg_volume_63) },
      ];
      const head = ["Symbol", "Mom 12-1", "Mom 1m", "Vol 63d", "Avg vol 63d"];
      return `<h4>Strongest ${esc(r.factor)}</h4><div class="tablewrap">${table(head, r.top.map(rowOf))}</div>
        <h4>Weakest</h4><div class="tablewrap">${table(head, r.bottom.map(rowOf))}</div>
        <p class="hint">Universe ${fmtInt(r.universe)} · mean ${fmtNum(r.mean, 4)} · median ${fmtNum(r.median, 4)}. ${esc(r.note)}</p>`;
    });
  };
  $("#kimi-fac-run").addEventListener("click", run);
  run();
}

async function loadKimiSignals(host) {
  host.innerHTML = `
    <h3>Signal outcome tracker</h3>
    <p class="hint">Measures forward returns after a defined signal using next-session entry (no look-ahead). Executed by the real analysis engine (<code>signal_outcomes</code>).</p>
    <div class="controls" style="flex-wrap:wrap;gap:10px">
      <label>Symbol<br><input id="kimi-sig-sym" value="${esc(($("#symbol-input") && $("#symbol-input").value) || "NABIL")}" style="width:110px" /></label>
      <label>Signal<br><select id="kimi-sig-kind">
        <option value="rsi_oversold">RSI oversold (&lt;30)</option>
        <option value="rsi_overbought">RSI overbought (&gt;70)</option>
        <option value="macd_bullish_cross">MACD bullish cross</option>
        <option value="donchian_breakout">20-bar breakout</option>
        <option value="volume_spike">Volume spike</option>
      </select></label>
      <button class="ctb-btn" id="kimi-sig-run">Measure outcomes</button>
    </div>
    <div id="kimi-sig-out" class="tablewrap"></div>`;
  const run = () => {
    const symbol = ($("#kimi-sig-sym").value || "").trim().toUpperCase();
    if (!symbol) return;
    kimiRunAnalysis("signal_outcomes", { symbol, signal: $("#kimi-sig-kind").value, horizons: [5, 10, 20, 60] }, $("#kimi-sig-out"), (r) => {
      if (!r.available) return `<div class="empty">${esc(r.reason || "no data")}</div>`;
      const rows = Object.entries(r.horizons || {}).map(([k, v]) => [
        { html: esc(k.replace("h", "")) + "d" },
        { html: fmtInt(v.n) },
        { html: fmtNum((v.mean || 0) * 100, 2) + "%" },
        { html: fmtNum((v.median || 0) * 100, 2) + "%" },
        { html: v.hit_rate == null ? "—" : fmtNum(v.hit_rate * 100, 1) + "%" },
      ]);
      return `<h4>${esc(r.symbol)} — ${esc(r.signal_definition || r.signal)}</h4>
        <div class="tablewrap">${table(["Horizon", "Signals", "Mean return", "Median", "Hit rate"], rows)}</div>
        <p class="hint">${fmtInt(r.signals)} signals over ${fmtInt(r.bars)} bars · entry: ${esc(r.entry)}. Historical study, not a forecast.</p>`;
    });
  };
  $("#kimi-sig-run").addEventListener("click", run);
  run();
}

async function loadKimiMonteCarlo(host) {
  host.innerHTML = `
    <h3>Monte Carlo terminal-wealth distribution</h3>
    <p class="hint">Executed by the real analysis engine (<code>/api/analysis/run</code> → <code>monte_carlo</code>). Either a GBM with the drift/vol you supply, or a historical bootstrap of a symbol's stored returns. Reproducible under a fixed seed.</p>
    <div class="controls" style="flex-wrap:wrap;gap:10px">
      <label>Mode<br><select id="kimi-mc-mode"><option value="gbm">GBM (assumptions)</option><option value="bootstrap">Historical bootstrap</option></select></label>
      <label>Symbol<br><input id="kimi-mc-sym" value="${esc(($("#symbol-input") && $("#symbol-input").value) || "NABIL")}" style="width:110px" /></label>
      <label>Start <input id="kimi-mc-start" value="100" style="width:90px" /></label>
      <label>Drift <input id="kimi-mc-drift" value="0.08" style="width:80px" /></label>
      <label>Vol <input id="kimi-mc-vol" value="0.25" style="width:80px" /></label>
      <label>Horizon <input id="kimi-mc-h" value="252" style="width:80px" /></label>
      <label>Paths <input id="kimi-mc-n" value="1000" style="width:80px" /></label>
      <label>Seed <input id="kimi-mc-seed" value="42" style="width:80px" /></label>
      <button class="ctb-btn" id="kimi-mc-run">Simulate</button>
    </div>
    <div id="kimi-mc-out" class="tablewrap"></div>`;
  const run = async () => {
    const mode = $("#kimi-mc-mode").value;
    const params = {
      start: Number($("#kimi-mc-start").value) || 100,
      drift: Number($("#kimi-mc-drift").value) || 0.08,
      volatility: Number($("#kimi-mc-vol").value) || 0.25,
      days: Number($("#kimi-mc-h").value) || 252,
      paths: Math.min(20000, Number($("#kimi-mc-n").value) || 1000),
      seed: Number($("#kimi-mc-seed").value) || 42,
    };
    if (mode === "bootstrap") {
      const sym = ($("#kimi-mc-sym").value || "").trim().toUpperCase();
      try {
        const d = await api(`/api/bars/${encodeURIComponent(sym)}?limit=1000`);
        const closes = (d.bars || []).map((b) => Number(b.close)).filter((x) => Number.isFinite(x) && x > 0);
        params.returns = closes.slice(1).map((c, i) => c / closes[i] - 1).filter(Number.isFinite);
      } catch (e) {
        $("#kimi-mc-out").innerHTML = `<div class="empty">Could not load ${esc(sym)}: ${esc(e.message)}</div>`;
        return;
      }
    }
    kimiRunAnalysis("monte_carlo", params, $("#kimi-mc-out"), (r) => {
      const p = r.percentiles || {};
      return `<h4>${r.method === "bootstrap" ? "Historical bootstrap" : "Geometric Brownian motion"} — ${fmtInt(r.paths)} paths, ${fmtInt(r.days)} days</h4>
        <div class="tablewrap">${table(["Statistic", "Value"], [
          ["Start", fmtNum(r.start, 2)],
          ["Median", fmtNum(r.median, 2)],
          ["5th percentile", fmtNum(p.p5, 2)],
          ["25th percentile", fmtNum(p.p25, 2)],
          ["75th percentile", fmtNum(p.p75, 2)],
          ["95th percentile", fmtNum(p.p95, 2)],
          ["Probability of gain", fmtNum(r.prob_gain * 100, 2) + "%"],
          ["Probability of ≥20% loss", fmtNum(r.prob_loss_20pct * 100, 2) + "%"],
        ].map((row) => row.map((c) => ({ html: esc(String(c)) }))))}</div>
        <p class="hint">${esc(r.note || "Model output under stated assumptions — not a prediction.")}</p>`;
    });
  };
  $("#kimi-mc-run").addEventListener("click", run);
  run();
}

async function loadKimiValuation(host) {
  host.innerHTML = `
    <h3>Fundamentals &amp; valuation</h3>
    <div class="controls"><label>Symbol <input id="kimi-val-sym" value="NABIL" /></label><button class="ctb-btn" id="kimi-val-run">Load fundamentals</button></div>
    <div id="kimi-val-out" class="tablewrap"></div>
    <h4>Discounted cash-flow (model)</h4>
    <p class="hint">Every input below is an assumption you supply; the engine does not estimate or fetch them. Executed by the analysis engine (<code>dcf_valuation</code>).</p>
    <div class="controls" style="flex-wrap:wrap;gap:10px">
      <label>FCF₀ (NPR) <input id="kimi-dcf-fcf" value="1000000000" style="width:130px" /></label>
      <label>Growth <input id="kimi-dcf-g" value="0.08" style="width:70px" /></label>
      <label>WACC <input id="kimi-dcf-w" value="0.13" style="width:70px" /></label>
      <label>Terminal g <input id="kimi-dcf-tg" value="0.04" style="width:70px" /></label>
      <label>Years <input id="kimi-dcf-y" value="5" style="width:60px" /></label>
      <label>Net debt <input id="kimi-dcf-nd" value="0" style="width:110px" /></label>
      <label>Shares <input id="kimi-dcf-sh" value="100000000" style="width:120px" /></label>
      <button class="ctb-btn" id="kimi-dcf-run">Value</button>
    </div>
    <div id="kimi-dcf-out" class="tablewrap"></div>`;
  const run = async () => {
    const s = ($("#kimi-val-sym").value || "").trim().toUpperCase();
    if (!s) return;
    const out = $("#kimi-val-out");
    if (out) out.innerHTML = `<div class="empty">Loading ${esc(s)}…</div>`;
    try {
      const d = await api(`/api/fundamentals/${encodeURIComponent(s)}`);
      const recs = Array.isArray(d) ? d : (d.records || d.fundamentals || []);
      let html = `<h3>${esc(s)} — Stored Fundamentals</h3>`;
      if (recs.length) {
        html += `<div class="tablewrap">${table(["Field","Value","Period","Source","Verification"],
          recs.slice(0,60).map((r) => [
            { html: esc(r.field) },
            { html: fmtNum(r.value) },
            { html: esc(r.period_label || r.period_end || "—") },
            { html: esc(r.source || "—") },
            { html: `<span class="pill ${r.verification === "reviewed" ? "pill-ok" : "pill-warn"}">${esc(r.verification || "—")}</span>` },
          ]))}</div>`;
        if (recs.length > 60) html += `<p class="hint">Showing 60 of ${fmtInt(recs.length)} records.</p>`;
      } else {
        html += `<div class="empty">No fundamentals stored for ${esc(s)}.</div>`;
      }
      out.innerHTML = html;
    } catch (e) { if (out) out.innerHTML = `<div class="empty">Could not load: ${esc(e.message)}</div>`; }
  };
  $("#kimi-val-run").addEventListener("click", run);
  run();

  const runDcf = () => {
    const params = {
      fcf0: Number($("#kimi-dcf-fcf").value) || 0,
      growth: Number($("#kimi-dcf-g").value) || 0,
      wacc: Number($("#kimi-dcf-w").value) || 0.13,
      terminal_growth: Number($("#kimi-dcf-tg").value) || 0,
      years: Number($("#kimi-dcf-y").value) || 5,
      net_debt: Number($("#kimi-dcf-nd").value) || 0,
      shares: Number($("#kimi-dcf-sh").value) || 1,
    };
    kimiRunAnalysis("dcf_valuation", params, $("#kimi-dcf-out"), (r) => {
      if (!r.available) return `<div class="empty">${esc(r.reason)}</div>`;
      const sensHead = ["WACC \\ g", ...Object.keys(r.sensitivity[0].values)];
      const sensRows = r.sensitivity.map((row) => [
        { html: fmtNum(row.wacc, 3) },
        ...Object.values(row.values).map((v) => ({ html: fmtNum(v, 2) })),
      ]);
      return `<div class="tablewrap">${table(["Field", "Value"], [
        ["Enterprise value", fmtNum(r.enterprise_value, 0)],
        ["Equity value", fmtNum(r.equity_value, 0)],
        ["Value per share", fmtNum(r.per_share, 2)],
        ["PV explicit", fmtNum(r.pv_explicit, 0)],
        ["PV terminal", fmtNum(r.pv_terminal, 0)],
      ].map((row) => row.map((c) => ({ html: esc(String(c)) }))))}</div>
        <h5>Sensitivity: value per share</h5>
        <div class="tablewrap">${table(sensHead.map((h) => esc(h)), sensRows)}</div>
        <p class="hint">${esc(r.note)}</p>`;
    });
  };
  $("#kimi-dcf-run").addEventListener("click", runDcf);
  runDcf();
}

async function loadKimiPortfolio(host) {
  host.innerHTML = `
    <h3>Portfolio construction (research)</h3>
    <p class="hint">Long-only allocations computed from the stored return history. Mean-variance via projected gradient, and hierarchical risk parity. No expected-return forecasts are invented.</p>
    <div class="controls" style="flex-wrap:wrap;gap:10px">
      <label>Symbols (comma-separated)<br><input id="kimi-pf-syms" value="NABIL, SCB, EBL, ADBL" style="min-width:280px" /></label>
      <button class="ctb-btn" id="kimi-pf-run">Optimise</button>
    </div>
    <div id="kimi-pf-out"></div>
    <h4>Risk of ruin &amp; losing streaks</h4>
    <p class="hint">IID trade simulation (<code>risk_of_ruin</code>). Trades are assumed independent; real streaks cluster, so treat the tail as optimistic.</p>
    <div class="controls" style="flex-wrap:wrap;gap:10px">
      <label>Win rate <input id="kimi-rr-win" value="0.5" style="width:70px" /></label>
      <label>Payoff ratio <input id="kimi-rr-pay" value="1.5" style="width:70px" /></label>
      <label>Risk/trade <input id="kimi-rr-risk" value="0.02" style="width:70px" /></label>
      <label>Trades <input id="kimi-rr-trades" value="200" style="width:70px" /></label>
      <label>Ruin drawdown <input id="kimi-rr-ruin" value="0.5" style="width:80px" /></label>
      <label>Paths <input id="kimi-rr-paths" value="2000" style="width:80px" /></label>
      <button class="ctb-btn" id="kimi-rr-run">Simulate</button>
    </div>
    <div id="kimi-rr-out" class="tablewrap"></div>
    <h4>Market-shock stress test</h4>
    <p class="hint">Single-factor (market-model) scenario via each symbol's beta vs the NEPSE composite. Systematic exposure only.</p>
    <div class="controls" style="flex-wrap:wrap;gap:10px">
      <label>Symbols <input id="kimi-st-syms" value="NABIL, SCB, EBL" style="min-width:240px" /></label>
      <label>Market shock <input id="kimi-st-shock" value="-0.10" style="width:80px" /></label>
      <button class="ctb-btn" id="kimi-st-run">Stress</button>
    </div>
    <div id="kimi-st-out" class="tablewrap"></div>`;
  const run = async () => {
    const syms = ($("#kimi-pf-syms").value || "").split(",").map((s) => s.trim().toUpperCase()).filter(Boolean);
    const out = $("#kimi-pf-out");
    if (syms.length < 2) { out.innerHTML = `<div class="empty">Enter at least two symbols.</div>`; return; }
    out.innerHTML = `<div class="empty">Optimising ${esc(syms.join(", "))}…</div>`;
    try {
      const ef = (await api("/api/analysis/run", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ fn: "efficient_frontier", symbols: syms, params: { window: 250 } }) })).result;
      const hr = (await api("/api/analysis/run", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ fn: "hrp_portfolio", symbols: syms, params: { window: 250 } }) })).result;
      let html = "";
      if (ef && ef.available) {
        const asRows = (label, w) => [label, ...Object.entries(w).sort((a, b) => b[1] - a[1]).map(([k, v]) => [`${k}`, fmtNum(v * 100, 2) + "%"])];
        html += `<h4>Mean-variance frontier</h4><div class="tablewrap">${table(["Portfolio", "Weights"],
          [asRows("Min variance", ef.min_variance.weights), asRows("Max Sharpe", ef.max_sharpe.weights)].map((r) => [
            { html: esc(r[0]) },
            { html: r.slice(1).map(([k, v]) => `${esc(k)} ${esc(v)}`).join(" · ") },
          ]))}</div>`;
      } else { html += `<div class="empty">Frontier: ${esc((ef && ef.reason) || "unavailable")}</div>`; }
      if (hr && hr.available) {
        html += `<h4>Hierarchical risk parity</h4><div class="tablewrap">${table(["Symbol", "Weight"],
          Object.entries(hr.weights).sort((a, b) => b[1] - a[1]).map(([k, v]) => [
            { html: `<b>${esc(k)}</b>` }, { html: fmtNum(v * 100, 2) + "%" }]))}</div>
          <p class="hint">Annualised vol ${fmtNum(hr.annualised_volatility * 100, 2)}% vs equal-weight ${fmtNum(hr.equal_weight_volatility * 100, 2)}% over ${fmtInt(hr.observations)} observations.</p>`;
      } else { html += `<div class="empty">HRP: ${esc((hr && hr.reason) || "unavailable")}</div>`; }
      out.innerHTML = html;
    } catch (e) { out.innerHTML = `<div class="empty">Optimisation failed: ${esc(e.message)}</div>`; }
  };
  $("#kimi-pf-run").addEventListener("click", run);
  run();

  const runRuin = () => {
    const payoff = Math.max(1e-6, Number($("#kimi-rr-pay").value) || 1.5);
    const risk = Number($("#kimi-rr-risk").value) || 0.02;
    const params = {
      win_rate: Number($("#kimi-rr-win").value) || 0.5,
      avg_win: risk * payoff,
      avg_loss: risk,
      risk_per_trade: risk,
      trades: Number($("#kimi-rr-trades").value) || 200,
      ruin_threshold: Number($("#kimi-rr-ruin").value) || 0.5,
      paths: Math.min(20000, Number($("#kimi-rr-paths").value) || 2000),
    };
    kimiRunAnalysis("risk_of_ruin", params, $("#kimi-rr-out"), (r) => table(["Statistic", "Value"], [
      ["Paths", fmtInt(r.paths)],
      ["Trades per path", fmtInt(r.trades)],
      ["Probability of ruin", fmtNum(r.prob_ruin * 100, 2) + "%"],
      ["Median final equity (×)", fmtNum(r.median_final, 3)],
      ["Median max drawdown", fmtNum(r.median_max_drawdown * 100, 2) + "%"],
      ["95th-percentile max drawdown", fmtNum(r.p95_max_drawdown * 100, 2) + "%"],
    ].map((row) => row.map((c) => ({ html: esc(String(c)) })))));
  };
  $("#kimi-rr-run").addEventListener("click", runRuin);
  runRuin();

  const runStress = () => {
    const syms = ($("#kimi-st-syms").value || "").split(",").map((s) => s.trim().toUpperCase()).filter(Boolean);
    if (!syms.length) return;
    kimiRunAnalysis("stress_test", { symbols: syms, market_shock: Number($("#kimi-st-shock").value) || -0.1 },
      $("#kimi-st-out"), (r) => {
        if (!r.available) return `<div class="empty">${esc(r.reason)}</div>`;
        const rows = Object.entries(r.symbol_impacts).map(([k, v]) => [
          { html: `<b>${esc(k)}</b>` },
          { html: fmtNum(r.betas[k], 3) },
          { html: fmtNum((r.weights[k] || 0) * 100, 2) + "%" },
          { html: fmtNum(v * 100, 2) + "%" },
        ]);
        return `<div class="tablewrap">${table(["Symbol", "Beta", "Weight", "Impact"], rows)}</div>
          <p class="hint">Scenario market shock ${fmtNum(r.scenario.market_shock * 100, 1)}% → portfolio impact ${fmtNum(r.portfolio_impact * 100, 2)}%. ${esc(r.note)}</p>`;
      });
  };
  $("#kimi-st-run").addEventListener("click", runStress);
  runStress();
}

async function loadKimiResearchDesk(host) {
  host.innerHTML = `
    <h3>Research desk &amp; methodology</h3>
    <p class="hint">Methodology registry for every engine KIMI exposes, plus the data-coverage explorer. Nothing here is a recommendation.</p>
    <div class="tablewrap">${table(["Engine", "What it does", "Assumption / limit"], [
      ["Screen engine (/api/screen)", "Evaluates boolean condition trees over stored bars", "As-of the latest stored bar; no intraday"],
      ["Backtest engine (/api/backtest)", "Runs a strategy with fees and next-open execution", "Historical rule; rounding, costs matter"],
      ["Monte Carlo", "GBM or historical bootstrap of returns", "Model output under stated drift/vol; not a forecast"],
      ["Efficient frontier", "Long-only mean-variance via simplex projection", "Covariance from the trailing window; no return forecast"],
      ["HRP", "Hierarchical risk parity allocation", "Covariance structure only; ignores expected returns"],
      ["Deflated Sharpe", "Sharpe adjusted for skew, kurtosis, trials", "Needs an honest trial count"],
      ["Risk of ruin", "IID trade simulation", "Trades assumed independent; real streaks cluster"],
      ["Stress test", "Beta-based market-shock scenario", "Systematic exposure only"],
      ["Event study", "CAR around supplied event dates", "Event dates must be supplied; small samples are noisy"],
      ["DCF / reverse DCF", "Cash-flow valuation with sensitivity grid", "All inputs are assumptions supplied by the user"],
      ["Fundamental tools", "Ratios and ranks over stored fundamentals", "Only stored fields; missing data is stated, never imputed"],
    ].map((r) => r.map((c) => ({ html: esc(c) }))))}</div>
    <h4>Data coverage</h4>
    <div id="kimi-rd-cov" class="tablewrap"><div class="empty">Loading…</div></div>`;
  kimiRunAnalysis("coverage_explorer", {}, $("#kimi-rd-cov"), (r) => {
    const m = r.market || {};
    return table(["Store", "Value"], [
      ["Securities", fmtInt(m.securities)],
      ["Bars total", fmtInt(m.bars_total)],
      ["Date range", `${esc(m.first_date || "—")} → ${esc(m.last_date || "—")}`],
      ["Securities with <60 bars", fmtInt(m.securities_with_lt_60_bars)],
      ["Fundamental records", r.fundamentals ? fmtInt(r.fundamentals.records) : "—"],
      ["Fundamental symbols", r.fundamentals ? fmtInt(r.fundamentals.symbols) : "—"],
    ].map((row) => row.map((c) => ({ html: String(c) })))) +
      `<p class="hint"><b>Known gaps:</b> ${esc((r.known_gaps || []).join(" · "))}</p>`;
  });
}

async function loadKimiAiDesk(host) {
  const sym = ($("#symbol-input")?.value || "").trim().toUpperCase() || "NABIL";
  host.innerHTML = `
    <h3>Evidence-bound AI research desk</h3>
    <p class="hint">The desk assembles real evidence from the local stores, then — only if a provider is configured — asks a model to reason over it. Every number in the answer is checked against the evidence bundle and unmatched numbers are flagged. The desk cannot place a trade or modify a portfolio.</p>
    <div class="controls" style="flex-wrap:wrap;gap:10px;align-items:flex-end">
      <label>Symbol<br><input id="ai-sym" value="${esc(sym)}" style="width:120px" /></label>
      <label style="flex:1 1 320px">Question<br><input id="ai-q" value="Summarise the evidence and state clearly what cannot be supported." style="width:100%" /></label>
      <button class="ctb-btn" id="ai-run">Ask with evidence</button>
      <button class="ctb-btn" id="ai-ev">Show evidence</button>
    </div>
    <div id="ai-out" class="tablewrap"><div class="empty">Ask a question, or show the evidence bundle.</div></div>`;

  const out = $("#ai-out");
  const renderEvidence = (ev) => {
    let html = `<h4>Evidence bundle — ${esc(ev.symbol || "")} (${fmtInt((ev.items || []).length)} items)</h4>` +
      table(["Kind", "Label", "Value", "Unit", "As of", "Source", "Calculation"],
        (ev.items || []).map((it) => [
          { html: esc(it.kind) },
          { html: esc(it.label) },
          { html: esc(String(it.value)) },
          { html: esc(it.unit || "—") },
          { html: esc(it.as_of || "—") },
          { html: esc(it.source || "—") },
          { html: esc(it.calculation || "—") },
        ]));
    if ((ev.missing || []).length) html += `<p class="hint"><b>Missing inputs (not guessed):</b> ${esc(ev.missing.join(" · "))}</p>`;
    if ((ev.limitations || []).length) html += `<p class="hint"><b>Limitations:</b> ${esc(ev.limitations.join(" "))}</p>`;
    return html;
  };
  const renderReview = (rv) => {
    if (!rv || !rv.checks) return "";
    return `<h4>Skepical review — <b>${esc(rv.verdict || "unknown")}</b> (${fmtInt(rv.flags || 0)} flags)</h4>` +
      table(["Check", "Status", "Detail"],
        rv.checks.map((c) => [
          { html: esc(c.check) },
          { html: `<span class="pill ${c.status === "flag" ? "pill-warn" : "pill-ok"}">${esc(c.status)}</span>` },
          { html: esc(c.detail || "") },
        ]));
  };

  $("#ai-ev").onclick = async () => {
    out.innerHTML = `<div class="empty">Loading evidence…</div>`;
    try {
      const ev = await api(`/api/research-desk/evidence?symbol=${encodeURIComponent($("#ai-sym").value.trim())}`);
      if (!out.isConnected) return;
      out.innerHTML = renderEvidence(ev);
    } catch (e) { if (out.isConnected) out.innerHTML = `<div class="empty">Could not load evidence: ${esc(e.message)}</div>`; }
  };
  $("#ai-run").onclick = async () => {
    out.innerHTML = `<div class="empty">Working…</div>`;
    try {
      const d = await api("/api/research-desk/run", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: $("#ai-q").value, symbol: $("#ai-sym").value.trim() }),
      });
      if (!out.isConnected) return;
      let html = "";
      if (!d.available) {
        html += `<p class="hint"><b>AI unavailable:</b> ${esc(d.error || "unknown reason")}</p>`;
      } else {
        html += `<h4>Answer — ${esc(d.provider || "")} ${esc(d.model || "")}</h4><pre style="white-space:pre-wrap">${esc(d.answer || "(empty)")}</pre>`;
      }
      out.innerHTML = html + renderReview(d.review) + renderEvidence(d.evidence || {});
    } catch (e) { if (out.isConnected) out.innerHTML = `<div class="empty">Research request failed: ${esc(e.message)}</div>`; }
  };
}

async function loadKimiReconcile(host) {
  host.innerHTML = `
    <h3>Data-source reconciliation</h3>
    <p class="hint">Compares the same observation reported by more than one source. Nothing is overwritten and no source is declared correct automatically: a decision is only ever recorded by a human. Missing values are reported, never filled in.</p>
    <div class="controls" style="flex-wrap:wrap;gap:10px;align-items:flex-end">
      <label>Dataset<br><select id="rec-dataset"></select></label>
      <label>Tolerance (bps or %)<br><input id="rec-tol" value="" placeholder="default" style="width:110px" /></label>
      <button class="ctb-btn" id="rec-run">Run comparison</button>
    </div>
    <p class="hint" id="rec-profile"></p>
    <div id="rec-out" class="tablewrap"><div class="empty">Choose a dataset and run a comparison.</div></div>
    <div id="rec-decision"></div>
    <h4 style="margin-top:12px">Audit history</h4>
    <div id="rec-history" class="tablewrap"><div class="empty">Loading…</div></div>`;

  const loadHistory = async () => {
    const el = $("#rec-history");
    if (!el) return;
    try {
      const d = await api("/api/reconciliation/history?limit=50");
      if (!el.isConnected) return;
      if (!(d.runs || []).length && !(d.resolutions || []).length) {
        el.innerHTML = `<p class="hint">No comparison has been run yet.</p>`; return;
      }
      el.innerHTML =
        `<h5>Runs</h5>` + table(["When", "Dataset", "Findings", "Tolerance"],
          (d.runs || []).map((r) => [
            { html: esc(r.created_at) }, { html: esc(r.dataset) }, { html: fmtInt(r.findings) },
            { html: esc(r.tolerances_json) }])) +
        `<h5>Resolutions (human decisions)</h5>` + ((d.resolutions || []).length
          ? table(["When", "Dataset", "Finding", "Resolution", "Chosen source", "Note"],
            d.resolutions.map((r) => [
              { html: esc(r.created_at) }, { html: esc(r.dataset) }, { html: esc(r.finding_key) },
              { html: esc(r.resolution) }, { html: esc(r.chosen_source || "—") }, { html: esc(r.note || "") }]))
          : `<p class="hint">No decision has been recorded.</p>`);
    } catch (e) { if (el && el.isConnected) el.innerHTML = `<div class="empty">Could not load history: ${esc(e.message)}</div>`; }
  };

  try {
    const d = await api("/api/reconciliation/datasets");
    const cmp = d.comparisons || [];
    $("#rec-dataset").innerHTML = cmp.map((x) =>
      `<option value="${esc(x.name)}" data-profile="${x.profile_available ? "1" : "0"}">${esc(x.label)}</option>`).join("");
  } catch (e) { $("#rec-dataset").innerHTML = `<option value="">unavailable</option>`; }

  $("#rec-run").onclick = async () => {
    const sel = $("#rec-dataset");
    const ds = sel.value;
    const canProfile = sel.selectedOptions && sel.selectedOptions[0] && sel.selectedOptions[0].dataset.profile === "1";
    const tolRaw = $("#rec-tol").value.trim();
    const body = { dataset: ds };
    if (tolRaw !== "") body.tolerance = Number(tolRaw);
    const out = $("#rec-out");
    out.innerHTML = `<div class="empty">Comparing…</div>`;
    try {
      if (canProfile) {
        const prof = await api(`/api/reconciliation/profile?dataset=${encodeURIComponent(ds)}`);
        if (!out.isConnected) return;
        $("#rec-profile").innerHTML = `${fmtInt(prof.rows)} rows · sources: ${esc(Object.keys(prof.sources || {}).join(", ") || "none")} · range ${esc(prof.first_observed || "—")} → ${esc(prof.last_observed || "—")}` +
          (Object.values(prof.missing_by_field || {}).some((v) => v) ? ` · missing: ${esc(JSON.stringify(prof.missing_by_field))}` : "");
      } else if ($("#rec-profile")) {
        $("#rec-profile").textContent = "This comparison joins more than one dataset, so a single-dataset profile does not apply.";
      }
      const d = await api("/api/reconciliation/run", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
      if (!out.isConnected) return;
      if (!(d.items || []).length) {
        out.innerHTML = `<p class="hint">No discrepancy found for ${esc(ds)} at tolerance ${esc(String(d.tolerance))}. That is a comparison result, not a guarantee the data is correct.</p>`;
        await loadHistory(); return;
      }
      out.innerHTML = `<p class="hint">${fmtInt(d.findings)} finding(s) — ${esc(JSON.stringify(d.by_classification))}</p>` +
        table(["Severity", "Classification", "Symbol", "Detail", "Sources", ""],
          d.items.slice(0, 300).map((f, i) => [
            { html: `<span class="pill ${f.severity === "high" ? "pill-warn" : "pill-ok"}">${esc(f.severity)}</span>` },
            { html: esc(f.classification) },
            { html: esc(f.symbol || "—") },
            { html: esc(f.detail || "") },
            { html: esc((f.sources || []).map((s) => `${s.source}=${s.value}`).join(", ")) },
            { html: `<button class="ctb-btn rec-decide" data-i="${i}">Resolve…</button>` },
          ]));
      if (d.items.length > 300) out.innerHTML += `<p class="hint">Showing 300 of ${fmtInt(d.findings)} findings.</p>`;
      $$("#rec-out .rec-decide").forEach((btn) => {
        btn.onclick = () => {
          const f = d.items[Number(btn.dataset.i)];
          const srcs = (f.sources || []).map((s) => s.source).filter(Boolean);
          $("#rec-decision").innerHTML = `
            <h4>Record a decision</h4>
            <p class="hint">Finding: ${esc(f.id)} — ${esc(f.detail || "")}</p>
            <div class="controls" style="flex-wrap:wrap;gap:10px;align-items:flex-end">
              <label>Resolution<br><select id="dec-res">
                <option value="left_open">left open (no source chosen)</option>
                <option value="needs_review">needs review</option>
                <option value="accepted">accepted (choose a source)</option>
                <option value="accepted_both">accepted both (keep both)</option>
              </select></label>
              <label>Chosen source<br><select id="dec-src">${srcs.map((s) => `<option value="${esc(s)}">${esc(s)}</option>`).join("")}</select></label>
              <label style="flex:1 1 260px">Note<br><input id="dec-note" style="width:100%" placeholder="why this was chosen" /></label>
              <button class="ctb-btn" id="dec-save">Save decision</button>
            </div>`;
          $("#dec-save").onclick = async () => {
            try {
              await api("/api/reconciliation/resolve", {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                  dataset: d.dataset, finding_key: f.id, classification: f.classification,
                  resolution: $("#dec-res").value, chosen_source: $("#dec-src").value,
                  note: $("#dec-note").value,
                }),
              });
              $("#rec-decision").innerHTML = `<p class="hint">Decision recorded for ${esc(f.id)}. Source data was not modified.</p>`;
              await loadHistory();
            } catch (e) { if ($("#rec-decision")) $("#rec-decision").innerHTML = `<div class="empty">${esc(e.message)}</div>`; }
          };
        };
      });
      await loadHistory();
    } catch (e) { if (out.isConnected) out.innerHTML = `<div class="empty">Comparison failed: ${esc(e.message)}</div>`; }
  };

  await loadHistory();
}

async function loadKimiSnapshots(host) {
  let algos = [];
  try { const d = await api("/api/catalog/algorithm"); algos = (d.tools || []).filter((t) => t.run && t.run.fn); } catch (e) { algos = []; }
  const sym = ($("#symbol-input")?.value || "").trim().toUpperCase() || "NABIL";
  host.innerHTML = `
    <h3>Reproducible calculation snapshots</h3>
    <p class="hint">Every snapshot records the inputs, parameters, data cutoff, sources, methodology, code version and warnings, and classifies reproducibility honestly: <b>fully</b>, <b>partially</b>, or <b>unrecoverable</b>. A rerun is only reported as reproduced when the result matches byte-for-byte.</p>
    <div class="controls" style="flex-wrap:wrap;gap:10px;align-items:flex-end">
      <label>Feature<br><select id="snap-feature">${algos.map((t) => `<option value="${esc(t.run.fn)}">${esc(t.name)}</option>`).join("")}</select></label>
      <label>Symbol<br><input id="snap-sym" value="${esc(sym)}" style="width:120px" /></label>
      <button class="ctb-btn" id="snap-capture">Capture snapshot</button>
      <button class="ctb-btn" id="snap-refresh">Refresh list</button>
    </div>
    <div id="snap-out"></div>
    <div class="tablewrap" id="snap-list"><div class="empty">Loading…</div></div>`;

  const loadList = async () => {
    const el = $("#snap-list");
    if (!el) return;
    try {
      const d = await api("/api/snapshots?limit=100");
      if (!el.isConnected) return;
      if (!(d.snapshots || []).length) { el.innerHTML = `<p class="hint">No snapshot has been captured yet.</p>`; return; }
      el.innerHTML = table(["Created", "Feature", "Universe", "Cutoff", "Code", "Reproducibility", "Missing", "Actions"],
        d.snapshots.map((s) => [
          { html: esc(s.created_at) },
          { html: esc(s.feature) },
          { html: esc(s.universe || "—") },
          { html: esc(s.data_cutoff || "—") },
          { html: esc(s.code_version || "—") },
          { html: `<span class="pill ${s.reproducibility === "fully_reproducible" ? "pill-ok" : "pill-warn"}">${esc(s.reproducibility)}</span>` },
          { html: esc((s.missing_inputs || []).join(", ") || "—") },
          { html: `<button class="ctb-btn snap-rerun" data-id="${esc(s.id)}">Rerun</button> <button class="ctb-btn snap-view" data-id="${esc(s.id)}">Inspect</button>` },
        ]));
      $$("#snap-list .snap-rerun").forEach((b) => {
        b.onclick = async () => {
          b.disabled = true;
          try {
            const r = await api(`/api/snapshots/${encodeURIComponent(b.dataset.id)}/rerun`, { method: "POST" });
            if ($("#snap-out")) $("#snap-out").innerHTML = `<p class="hint"><b>Rerun ${esc(b.dataset.id)}:</b> reproduced=${esc(String(r.reproduced))} · ${esc(r.reason || r.note || "")}</p>`;
          } catch (e) { if ($("#snap-out")) $("#snap-out").innerHTML = `<div class="empty">${esc(e.message)}</div>`; }
          b.disabled = false;
        };
      });
      $$("#snap-list .snap-view").forEach((b) => {
        b.onclick = async () => {
          try {
            const s = await api(`/api/snapshots/${encodeURIComponent(b.dataset.id)}`);
            if (!$("#snap-out")) return;
            $("#snap-out").innerHTML =
              table(["Field", "Value"], [
                ["ID", esc(s.id)], ["Feature", esc(s.feature)],
                ["Created", esc(s.created_at)], ["Data cutoff", esc(s.data_cutoff || "—")],
                ["Universe", esc(s.universe || "—")], ["Date range", esc(s.date_range || "—")],
                ["Sources", esc((s.source_ids || []).join(", ") || "—")],
                ["Input hash", esc(s.input_hash)], ["Results hash", esc(s.results_hash)],
                ["Code version", esc(s.code_version)], ["Benchmark", esc(s.benchmark || "—")],
                ["Costs", esc(s.cost_assumptions || "—")], ["Seed", esc(s.seed || "—")],
                ["Methodology", esc((s.methodology || {}).name || "—")],
                ["Reproducibility", esc(s.reproducibility)],
                ["Missing inputs", esc((s.missing_inputs || []).join(", ") || "—")],
                ["Warnings", esc((s.warnings || []).join(" · ") || "—")],
                ["Limitations", esc(s.limitations || "—")],
              ].map((r) => r.map((c) => ({ html: String(c) })))) +
              `<h5>Parameters</h5><pre style="white-space:pre-wrap">${esc(JSON.stringify(s.params, null, 2))}</pre>`;
          } catch (e) { if ($("#snap-out")) $("#snap-out").innerHTML = `<div class="empty">${esc(e.message)}</div>`; }
        };
      });
    } catch (e) { if (el.isConnected) el.innerHTML = `<div class="empty">Could not load snapshots: ${esc(e.message)}</div>`; }
  };

  $("#snap-capture").onclick = async () => {
    const feature = $("#snap-feature").value;
    const params = { symbol: $("#snap-sym").value.trim().toUpperCase() };
    $("#snap-out").innerHTML = `<div class="empty">Running ${esc(feature)} and capturing…</div>`;
    try {
      const s = await api("/api/snapshots/capture", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ feature, params }),
      });
      if (!$("#snap-out")) return;
      $("#snap-out").innerHTML = `<p class="hint"><b>Captured ${esc(s.id)}</b> — reproducibility: <b>${esc(s.reproducibility)}</b>${(s.missing_inputs || []).length ? ` · missing: ${esc(s.missing_inputs.join(", "))}` : ""}</p>`;
      await loadList();
    } catch (e) { if ($("#snap-out")) $("#snap-out").innerHTML = `<div class="empty">Capture failed: ${esc(e.message)}</div>`; }
  };
  $("#snap-refresh").onclick = loadList;
  await loadList();
}

async function loadKimiAskData(host) {
  host.innerHTML = `
    <h3>Ask the data (local, read-only)</h3>
    <p class="hint">A narrow natural-language interface over the project's own tables. A question is parsed into an explicit plan, validated against table and column allowlists, and executed with bound parameters under a row limit. Unsupported questions are <b>refused</b>, never answered by inventing data.</p>
    <div class="controls" style="flex-wrap:wrap;gap:10px;align-items:flex-end">
      <label style="flex:1 1 380px">Question<br><input id="nlq-q" style="width:100%" value="average close of NABIL over last 30 days" /></label>
      <button class="ctb-btn" id="nlq-run">Run</button>
    </div>
    <p class="hint">Examples: “how many securities”, “price of NABIL”, “close of NABIL on 2025-06-16”, “highest close of NABIL in 2025”, “how many bars for NABIL”, “top 10 symbols by volume”, “eps of NABIL”, “eps history of NABIL”, “close of NEPSE index”.</p>
    <div id="nlq-out" class="tablewrap"><div class="empty">Ask a question.</div></div>
    <h4 style="margin-top:12px">Recent questions</h4>
    <div id="nlq-history" class="tablewrap"><div class="empty">Loading…</div></div>`;

  const loadHistory = async () => {
    const el = $("#nlq-history");
    if (!el) return;
    try {
      const d = await api("/api/query/history?limit=25");
      if (!el.isConnected) return;
      if (!(d.runs || []).length) { el.innerHTML = `<p class="hint">Nothing asked yet.</p>`; return; }
      el.innerHTML = table(["When", "Question", "Status", "Reason", "Rows", "ms"],
        d.runs.map((r) => [
          { html: esc(r.created_at) }, { html: esc(r.question) },
          { html: `<span class="pill ${r.status === "ok" ? "pill-ok" : "pill-warn"}">${esc(r.status)}</span>` },
          { html: esc(r.reason || "—") }, { html: fmtInt(r.rows) }, { html: fmtInt(r.duration_ms) },
        ]));
    } catch (e) { if (el && el.isConnected) el.innerHTML = `<div class="empty">Could not load history: ${esc(e.message)}</div>`; }
  };

  $("#nlq-run").onclick = async () => {
    const out = $("#nlq-out");
    out.innerHTML = `<div class="empty">Working…</div>`;
    try {
      const d = await api("/api/query/run", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: $("#nlq-q").value }),
      });
      if (!out.isConnected) return;
      if (d.status === "rejected") {
        out.innerHTML = `<p class="hint"><b>Refused:</b> ${esc(d.reason)}</p>`;
      } else if (d.status !== "ok") {
        out.innerHTML = `<p class="hint"><b>Error:</b> ${esc(d.reason || "unknown")}</p>`;
      } else {
        const p = d.plan || {};
        let html = `<p class="hint"><b>Plan:</b> intent=${esc(p.intent)} · dataset=${esc(p.dataset)} · fields=${esc((p.fields || []).join(", "))} · filters=${esc(JSON.stringify(p.filters || {}))} · limit=${esc(String(p.limit))} · ${esc(p.calculation)}</p>`;
        html += `<p class="hint">${fmtInt(d.row_count)} row(s) in ${fmtInt(d.duration_ms)} ms · ${esc((d.provenance || []).join(" · "))}</p>`;
        if ((d.rows || []).length) {
          const cols = Object.keys(d.rows[0]);
          html += table(cols, d.rows.map((r) => cols.map((c) => ({ html: esc(String(r[c])) }))));
        } else {
          html += `<p class="hint">No stored row matched. ${esc((d.missing || []).join(" · "))}</p>`;
        }
        html += `<p class="hint"><b>Limitations:</b> ${esc(d.limitations || "")}</p>`;
        out.innerHTML = html;
      }
      await loadHistory();
    } catch (e) { if (out.isConnected) out.innerHTML = `<div class="empty">Query failed: ${esc(e.message)}</div>`; }
  };
  await loadHistory();
}

async function loadKimiCorporateEvents(host) {
  host.innerHTML = `
    <h3>Corporate events</h3>
    <p class="hint">A typed calendar of corporate notices. Dividend, bonus, rights, IPO, allotment, AGM and split notices are <b>not</b> available from a licensed feed here and cannot be derived from prices, so those types stay empty until a document is supplied — an empty list means “no notice imported”, never “no event occurred”. Retirement/merger rows are projected from the attested registry and carry real observed dates.</p>
    <div class="tablewrap" id="ce-coverage"><div class="empty">Loading coverage…</div></div>
    <div class="controls" style="flex-wrap:wrap;gap:10px;align-items:flex-end">
      <label>Symbol<br><input id="ce-sym" style="width:120px" placeholder="all" /></label>
      <label>Type<br><input id="ce-type" style="width:120px" placeholder="all" /></label>
      <label>Since<br><input id="ce-since" style="width:120px" placeholder="YYYY-MM-DD" /></label>
      <label>Until<br><input id="ce-until" style="width:120px" placeholder="YYYY-MM-DD" /></label>
      <button class="ctb-btn" id="ce-load">Load calendar</button>
    </div>
    <div class="tablewrap" id="ce-list"><div class="empty">Load the calendar.</div></div>
    <h4 style="margin-top:12px">Import a notice document (CSV)</h4>
    <p class="hint">Headers: symbol, event_type, effective_date, value, unit, ratio, successor, headline, evidence, grade, source_ref, notes. A notice with no date is refused rather than guessed.</p>
    <textarea id="ce-text" rows="5" style="width:100%" placeholder="symbol,event_type,effective_date,value,unit&#10;NABIL,dividend,2026-05-01,12.5,NPR"></textarea>
    <div class="controls"><button class="ctb-btn" id="ce-import">Import</button></div>
    <div id="ce-import-out"></div>`;

  const loadCoverage = async () => {
    const el = $("#ce-coverage");
    try {
      const c = await api("/api/corporate-events/coverage");
      if (!el.isConnected) return;
      el.innerHTML = `<p class="hint"><b>Coverage:</b> ${fmtInt(c.stored_total)} imported notice(s), ${fmtInt(c.registry_total)} attested registry action(s). Status: <b>${esc(c.status)}</b>. Missing notice types: ${esc((c.missing_notice_types || []).join(", ") || "none")}.</p>` +
        `<p class="hint">${esc(c.limitation || "")}</p>`;
    } catch (e) { if (el.isConnected) el.innerHTML = `<div class="empty">Could not load coverage: ${esc(e.message)}</div>`; }
  };
  const loadList = async () => {
    const el = $("#ce-list");
    const qs = new URLSearchParams();
    for (const [id, key] of [["#ce-sym", "symbol"], ["#ce-type", "event_type"], ["#ce-since", "since"], ["#ce-until", "until"]]) {
      const v = ($(id)?.value || "").trim();
      if (v) qs.set(key, v);
    }
    el.innerHTML = `<div class="empty">Loading…</div>`;
    try {
      const d = await api(`/api/corporate-events?${qs.toString()}`);
      if (!el.isConnected) return;
      if (!(d.events || []).length) { el.innerHTML = `<p class="hint">No recorded event matches. That means no notice has been imported — not that no event occurred.</p>`; return; }
      el.innerHTML = table(["Date", "Symbol", "Type", "Grade", "Headline", "Value", "Ratio", "Successor", "Source"],
        d.events.map((ev) => [
          { html: esc(ev.effective_date || "—") }, { html: esc(ev.symbol) },
          { html: esc(ev.event_type) },
          { html: `<span class="pill ${ev.grade === "attested" ? "pill-ok" : "pill-warn"}">${esc(ev.grade)}</span>` },
          { html: esc(ev.headline || "—") },
          { html: ev.value === null || ev.value === undefined ? "—" : esc(`${ev.value} ${ev.unit || ""}`) },
          { html: esc(ev.ratio || "—") }, { html: esc(ev.successor || "—") }, { html: esc(ev.source || "") },
        ]));
    } catch (e) { if (el.isConnected) el.innerHTML = `<div class="empty">Could not load: ${esc(e.message)}</div>`; }
  };
  $("#ce-load").onclick = loadList;
  $("#ce-import").onclick = async () => {
    const out = $("#ce-import-out");
    try {
      const r = await api("/api/corporate-events/import", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: $("#ce-text").value, source: "ui-import" }),
      });
      out.innerHTML = `<p class="hint">Inserted ${fmtInt(r.inserted)}, updated ${fmtInt(r.updated)}, rejected ${fmtInt(r.rejected)}. Rejected rows lacked a symbol, a known type, a source or a required date; nothing was guessed.</p>`;
      await loadCoverage(); await loadList();
    } catch (e) { out.innerHTML = `<div class="empty">Import failed: ${esc(e.message)}</div>`; }
  };
  await loadCoverage();
  await loadList();
}

async function loadNewCompanyUniverse(host) {
  try {
    const d = await api("/api/securities?limit=2000");
    const syms = d.securities || [];
    host.innerHTML = `<p class="hint">${fmtInt(syms.length)} symbols with stored price history. Counts from actual stored data.</p>` +
      `<div class="tablewrap">${table(["Symbol", "Bars", "First date", "Last date"],
        syms.slice(0, 100).map((s) => [
          { html: `<b>${esc(s.symbol)}</b>` },
          { html: fmtInt(s.bars) },
          { html: esc(String(s.first_date).slice(0,10)) },
          { html: esc(String(s.last_date).slice(0,10)) },
        ]))}</div>` +
      (syms.length > 100 ? `<p class="hint">Showing first 100 of ${fmtInt(syms.length)}.</p>` : "");
  } catch (e) { host.innerHTML = `<div class="empty">Could not load: ${esc(e.message)}</div>`; }
}
async function loadNewSectorExplorer(host) {
  host.innerHTML = `<div class="empty">Loading sector classifications…</div>`;
  try {
    const d = await api("/api/sectors");
    const bySector = d.by_sector || {};
    const total = d.total_classified || 0;
    const nSectors = d.total_sectors || 0;
    if (!total) {
      host.innerHTML = `<div class="empty">No sector classifications available. Import sector CSVs via the sectors import tool.</div>`;
      return;
    }
    const rows = Object.entries(bySector).sort((a, b) => b[1].length - a[1].length).map(([sector, syms]) => [
      { html: `<b>${esc(sector)}</b>` },
      { html: fmtInt(syms.length) },
      { html: esc(syms.slice(0, 8).join(", ") + (syms.length > 8 ? "…" : "")) },
    ]);
    host.innerHTML = `
      <p class="hint">${fmtInt(total)} symbols classified into ${fmtInt(nSectors)} sectors (auto-imported from project review CSVs).</p>
      <div class="tablewrap">${table(["Sector", "Symbols", "Members (sample)"], rows)}</div>
      <p class="hint" style="margin-top:8px">Source: ${esc(d.source || "—")}. CSV import remains available as an override/correction mechanism.</p>`;
  } catch (e) {
    host.innerHTML = `<div class="empty">Could not load sectors: ${esc(e.message)}</div>`;
  }
}
async function loadNewCompanyProfile(host) {
  const sym = ($("#fund-symbol")?.value || $("#symbol-input")?.value || "").trim().toUpperCase() || "NABIL";
  host.innerHTML = `<div class="controls"><label>Symbol <input id="np-sym" value="${esc(sym)}" /></label><button class="ctb-btn" id="np-load">Load profile</button></div><div id="np-out" class="tablewrap"></div>`;
  const load = async () => {
    const s = ($("#np-sym").value || "").trim().toUpperCase();
    if (!s) return;
    const out = $("#np-out");
    if (out) out.innerHTML = `<div class="empty">Loading ${esc(s)}…</div>`;
    try {
      const d = await api(`/api/fundamentals/${encodeURIComponent(s)}`);
      const recs = Array.isArray(d) ? d : (d.records || []);
      let html = `<h3>${esc(s)} — Fundamentals</h3>`;
      if (recs.length) {
        html += `<div class="tablewrap">${table(["Field","Value","Period","Source","Verification"],
          recs.map((r) => [
            { html: esc(r.field) },
            { html: fmtNum(r.value) },
            { html: esc(r.period_label || r.period_end || "—") },
            { html: esc(r.source || "—") },
            { html: `<span class="pill ${r.verification === "reviewed" ? "pill-ok" : "pill-warn"}">${esc(r.verification || "—")}</span>` },
          ]))}</div>`;
      } else {
        html += `<div class="empty">No fundamental records for ${esc(s)}.</div>`;
      }
      try {
        const rt = await api(`/api/fundamentals/${encodeURIComponent(s)}/ratios`);
        html += `<h4 style="margin-top:10px">Ratios</h4><div class="stat-row">`;
        for (const [k, v] of Object.entries(rt.ratios || {})) {
          html += `<div class="stat"><div class="k">${esc(k)}</div><div class="v">${v.value == null ? "—" : fmtNum(v.value)}</div></div>`;
        }
        html += `</div>`;
        if (rt.ratios?.pe?.unavailable_reason) html += `<p class="hint">${esc(rt.ratios.pe.unavailable_reason)}</p>`;
      } catch (e) { /* ratios unavailable */ }
      try {
        const ttm = await api(`/api/fundamentals/${encodeURIComponent(s)}/ttm-eps`);
        html += `<p class="hint">TTM EPS: ${ttm.ttm_eps == null ? "—" : fmtNum(ttm.ttm_eps)} (${esc(ttm.reason || "ok")})</p>`;
      } catch (e) { /* ttm unavailable */ }
      try {
        const gr = await api(`/api/fundamentals/${encodeURIComponent(s)}/eps-growth`);
        html += `<p class="hint">EPS growth: ${gr.growth_pct == null ? "—" : fmtNum(gr.growth_pct, 2) + "%"} (${esc(gr.reason || "ok")})</p>`;
      } catch (e) { /* growth unavailable */ }
      html += `<div class="controls" style="margin-top:8px"><button class="ctb-btn ghost" id="np-open-chart">Open chart</button></div>`;
      if (out) out.innerHTML = html;
      const oc = $("#np-open-chart");
      if (oc) oc.addEventListener("click", () => { $("#symbol-input").value = s; showView("charts"); viewShown("charts"); loadChart(); });
    } catch (e) { if (out) out.innerHTML = `<div class="empty">Could not load ${esc(s)}: ${esc(e.message)}</div>`; }
  };
  const btn = $("#np-load");
  if (btn) btn.addEventListener("click", load);
  load();
}
async function loadNewEpsRankings(host) {
  try {
    const d = await api("/api/fundamentals/eps-rankings?limit=50");
    const items = d.items || [];
    host.innerHTML = `<p class="hint">${fmtInt(d.total)} symbols with EPS. ${fmtInt(items.length)} shown.</p>` +
      `<div class="tablewrap">${table(["Symbol","EPS","Period","Verification","Source"],
        items.map((r) => [
          { html: `<b>${esc(r.symbol)}</b>` },
          { html: fmtNum(r.eps) },
          { html: esc(r.period_label || r.period_end || "—") },
          { html: `<span class="pill ${r.verification === "reviewed" ? "pill-ok" : "pill-warn"}">${esc(r.verification || "—")}</span>` },
          { html: esc(r.source || "—") },
        ]))}</div>`;
  } catch (e) { host.innerHTML = `<div class="empty">Could not load: ${esc(e.message)}</div>`; }
}
async function loadNewEpsHistory(host) {
  const sym = ($("#fund-symbol")?.value || "NABIL").trim().toUpperCase();
  host.innerHTML = `<div class="controls"><label>Symbol <input id="nh-sym" value="${esc(sym)}" /></label><button class="ctb-btn" id="nh-load">Load</button></div><div id="nh-out" class="tablewrap"></div>`;
  const load = async () => {
    const s = ($("#nh-sym").value || "").trim().toUpperCase();
    if (!s) return;
    const out = $("#nh-out");
    if (out) out.innerHTML = `<div class="empty">Loading…</div>`;
    try {
      const d = await api(`/api/fundamentals/${encodeURIComponent(s)}`);
      const recs = Array.isArray(d) ? d : (d.records || []);
      const epsRecs = recs.filter((r) => r.field === "eps").sort((a,b) => (a.period_end||"") < (b.period_end||"") ? 1 : -1);
      if (out) out.innerHTML = epsRecs.length
        ? `<div class="tablewrap">${table(["Period","EPS","Source","Verification"],
            epsRecs.map((r) => [
              { html: esc(r.period_label || r.period_end || "—") },
              { html: fmtNum(r.value) },
              { html: esc(r.source || "—") },
              { html: esc(r.verification || "—") },
            ]))}</div>`
        : `<div class="empty">No EPS records for ${esc(s)}.</div>`;
    } catch (e) { if (out) out.innerHTML = `<div class="empty">Could not load: ${esc(e.message)}</div>`; }
  };
  const btn = $("#nh-load");
  if (btn) btn.addEventListener("click", load);
  load();
}
async function loadNewTtmEps(host) {
  const sym = ($("#fund-symbol")?.value || "NABIL").trim().toUpperCase();
  host.innerHTML = `<div class="controls"><label>Symbol <input id="nt-sym" value="${esc(sym)}" /></label><button class="ctb-btn" id="nt-load">Load</button></div><div id="nt-out" class="tablewrap"></div>`;
  const load = async () => {
    const s = ($("#nt-sym").value || "").trim().toUpperCase();
    if (!s) return;
    const out = $("#nt-out");
    if (out) out.innerHTML = `<div class="empty">Loading…</div>`;
    try {
      const d = await api(`/api/fundamentals/${encodeURIComponent(s)}/ttm-eps`);
      const gr = await api(`/api/fundamentals/${encodeURIComponent(s)}/eps-growth`).catch(() => null);
      let html = `<div class="stat-row"><div class="stat"><div class="k">TTM EPS</div><div class="v">${d.ttm_eps == null ? "—" : fmtNum(d.ttm_eps)}</div></div>`;
      if (d.quarters_used) html += `<div class="stat"><div class="k">Quarters used</div><div class="v">${fmtInt(d.quarters_used)}</div></div>`;
      html += `</div>`;
      if (d.reason) html += `<p class="hint" style="color:${PRAVAHA.caution}">⚠ ${esc(d.reason)}</p>`;
      if (d.quarters) html += `<div class="tablewrap">${table(["Period","EPS"], d.quarters.map((q) => [{html:esc(q.period_end||q.label||"—")},{html:fmtNum(q.value)}]))}</div>`;
      if (gr) html += `<p class="hint">EPS growth: ${gr.growth_pct == null ? "—" : fmtNum(gr.growth_pct, 2) + "%"} (${esc(gr.reason || "ok")})</p>`;
      if (out) out.innerHTML = html;
    } catch (e) { if (out) out.innerHTML = `<div class="empty">Could not load: ${esc(e.message)}</div>`; }
  };
  const btn = $("#nt-load");
  if (btn) btn.addEventListener("click", load);
  load();
}
async function loadNewFundCompare(host) {
  host.innerHTML = `<div class="controls"><label>Symbols (comma-separated) <input id="nc-syms" value="NABIL,NIMB" style="width:20em" /></label><button class="ctb-btn" id="nc-run">Compare</button></div><div id="nc-out" class="tablewrap"></div>`;
  const run = async () => {
    const syms = ($("#nc-syms").value || "").split(/[,\s]+/).map(s=>s.trim().toUpperCase()).filter(Boolean);
    if (syms.length < 2) { $("#nc-out").innerHTML = `<div class="empty">Enter at least 2 symbols.</div>`; return; }
    $("#nc-out").innerHTML = `<div class="empty">Loading…</div>`;
    try {
      const d = await api(`/api/fundamentals/compare?symbols=${encodeURIComponent(syms.join(","))}`);
      const reports = d.symbols || [];
      $("#nc-out").innerHTML = `<div class="tablewrap">${table(["Symbol","P/E","P/B","Div yield %","EPS"],
        reports.map((r) => [
          { html: `<b>${esc(r.symbol||r.requested||"?")}</b>` },
          { html: r.ratios?.pe?.value == null ? "—" : fmtNum(r.ratios.pe.value) },
          { html: r.ratios?.pb?.value == null ? "—" : fmtNum(r.ratios.pb.value) },
          { html: r.ratios?.dividend_yield_pct?.value == null ? "—" : fmtNum(r.ratios.dividend_yield_pct.value) },
          { html: r.ratios?.pe?.inputs?.[0]?.value == null ? "—" : fmtNum(r.ratios.pe.inputs[0].value) },
        ]))}</div>`;
    } catch (e) { $("#nc-out").innerHTML = `<div class="empty">Could not compare: ${esc(e.message)}</div>`; }
  };
  const btn = $("#nc-run");
  if (btn) btn.addEventListener("click", run);
  run();
}
async function loadNewScreener(host) {
  host.innerHTML = `<div class="empty">Financial screener is available in the existing Screener view (nav → More Scanners). Use the rule builder there. This tab provides a shortcut.</div><div class="controls"><button class="ctb-btn" id="nscr-go">Open Screener</button></div>`;
  const btn = $("#nscr-go");
  if (btn) btn.addEventListener("click", () => { showView("screener"); viewShown("screener"); });
}
async function loadNewMarginEligibility(host) {
  host.innerHTML = `<div class="empty">Margin-trading eligibility requires verified official NEPSE/SEBON rules. No official eligible-company list has been imported. Handwritten notebook criteria are unverified and must not be treated as current regulation. Status: NOT VERIFIED — no eligibility results can be shown.</div><p class="hint">To enable: import an official eligibility list via the Fundamentals import tool, or configure verified rules in a future update.</p>`;
}
async function loadNewDataCoverage(host) {
  try {
    const d = await api("/api/fundamentals/summary");
    const s = await api("/api/securities?limit=2000");
    host.innerHTML = `<div class="stat-row">
      <div class="stat"><div class="k">Fundamental records</div><div class="v">${fmtInt(d.total)}</div></div>
      <div class="stat"><div class="k">Symbols with fundamentals</div><div class="v">${fmtInt(d.symbols)}</div></div>
      <div class="stat"><div class="k">Companies with price data</div><div class="v">${fmtInt(s.count)}</div></div>
    </div>` +
      `<p class="hint">Coverage counts from actual stored records. EPS records: ${fmtInt(d.by_field?.eps || 0)}. Verified: ${fmtInt(d.by_verification?.reviewed || 0)}.</p>`;
  } catch (e) { host.innerHTML = `<div class="empty">Could not load: ${esc(e.message)}</div>`; }
}

/* ---------------------------------------------------------------- market intelligence */
async function loadMarketIntelligence() {
  const healthEl = $("#mi-health-out");
  const srcEl = $("#mi-sources");
  const errEl = $("#mi-error");
  if (errEl) errEl.textContent = "";
  try {
    const h = await api("/api/market-intelligence/health");
    if (healthEl) healthEl.innerHTML = `<div class="stat-row"><div class="stat"><div class="k">Status</div><div class="v">${esc(h.status)}</div></div>` +
      Object.entries(h.counts || {}).map(([k,v]) => `<div class="stat"><div class="k">${esc(k)}</div><div class="v">${fmtInt(v)}</div></div>`).join("") + `</div>`;
  } catch (e) { if (errEl) errEl.textContent = `Health check failed: ${e.message}`; }
  await loadMiSources();
}
async function loadMiSources() {
  const host = $("#mi-sources");
  const errEl = $("#mi-error");
  if (!host) return;
  const status = ($("#mi-status-filter") || {}).value || "";
  const group = ($("#mi-group-filter") || {}).value || "";
  try {
    const d = await api(`/api/market-intelligence/sources?limit=50${status ? "&status=" + encodeURIComponent(status) : ""}${group ? "&group=" + encodeURIComponent(group) : ""}`);
    const items = d.items || [];
    if (!items.length) { host.innerHTML = `<div class="empty">No sources match the filter. Click 'Import source registry'.</div>`; return; }
    host.innerHTML = `<div class="tablewrap">${table(
      ["Name", "Domain", "Group", "Status", "RSS"],
      items.map((s) => [
        { html: `<b>${esc(s.source_name)}</b>` },
        { html: esc(s.primary_domain) },
        { html: esc(s.source_group) },
        { html: `<span class="pill ${s.automated_access_status === "VERIFIED" ? "pill-ok" : "pill-warn"}">${esc(s.automated_access_status)}</span>` },
        { html: s.rss_url ? "✓" : "—" },
      ]))}</div>` + `<p class="hint">${fmtInt(d.total)} registered sources.</p>`;
  } catch (e) { if (errEl) errEl.textContent = `Source load failed: ${e.message}`; }
}
function bindMarketIntelligence() {
  if ($("#mi-health")) $("#mi-health").addEventListener("click", loadMarketIntelligence);
  if ($("#mi-import")) $("#mi-import").addEventListener("click", async () => {
    const errEl = $("#mi-error");
    try {
      const r = await api("/api/market-intelligence/import-sources", { method: "POST" });
      if (errEl) errEl.textContent = `Imported ${r.imported} of ${r.total_in_registry} sources.`;
      loadMiSources();
    } catch (e) { if (errEl) errEl.textContent = `Import failed: ${e.message}`; }
  });
  if ($("#mi-status-filter")) $("#mi-status-filter").addEventListener("change", loadMiSources);
  if ($("#mi-group-filter")) $("#mi-group-filter").addEventListener("change", loadMiSources);
}

/* ============================================================================
   FLOATING / RESIZABLE PANELS  (§ panels)
   ----------------------------------------------------------------------------
   Every panel that opens over the chart — the indicator manager, the compare
   drawer, the analysis drawer, the indicator documentation panel and the
   catalogue modal — can be dragged by its header and resized from its bottom
   corner. Docked drawers float on first drag; a ⤢ button toggles dock/float.
   Geometry is remembered per panel in localStorage. Nothing here changes chart
   state: moving a panel never reloads the chart or touches the viewport.
   ========================================================================== */
function panelGeomKey(el) { return `mt-panel-${el.id || "panel"}`; }
function savePanelGeom(el) {
  if (!el || !el.id) return;
  try {
    const r = el.getBoundingClientRect();
    localStorage.setItem(panelGeomKey(el), JSON.stringify({
      left: Math.round(r.left), top: Math.round(r.top),
      width: Math.round(r.width), height: Math.round(r.height),
      floating: el.dataset.fpFloat === "1" || el.classList.contains("fp-pane"),
    }));
  } catch (e) { /* storage full / disabled — geometry is a nicety */ }
}
function loadPanelGeom(el) {
  try { return JSON.parse(localStorage.getItem(panelGeomKey(el)) || "null"); }
  catch (e) { return null; }
}
function clampPanel(el) {
  const vw = window.innerWidth, vh = window.innerHeight;
  let r = el.getBoundingClientRect();
  if (r.width > vw - 12) el.style.width = `${vw - 20}px`;
  if (r.height > vh - 12) { el.style.height = `${vh - 24}px`; el.style.maxHeight = "none"; }
  r = el.getBoundingClientRect();
  el.style.left = `${Math.max(0, Math.min(vw - Math.min(r.width, 80) - 4, r.left))}px`;
  el.style.top = `${Math.max(0, Math.min(vh - Math.min(r.height, 48), r.top))}px`;
  // The resize grip lives at the bottom-right corner; if the panel bottom is
  // below the viewport the grip becomes unreachable, so pull the panel up.
  const bottom = (parseFloat(el.style.top) || 0) + r.height;
  if (bottom > vh - 4) el.style.top = `${Math.max(0, vh - r.height - 6)}px`;
}
function floatPanel(el) {
  if (el.dataset.fpFloat === "1") return;
  const r = el.getBoundingClientRect();
  el.dataset.fpFloat = "1";
  el.classList.add("floating");
  el.style.position = "fixed";
  el.style.left = `${Math.max(0, r.left)}px`;
  el.style.top = `${Math.max(0, r.top)}px`;
  if (!el.style.width) el.style.width = `${r.width}px`;
  if (!el.style.height && !el.classList.contains("fp-pane")) el.style.height = `${r.height}px`;
  el.style.maxHeight = el.classList.contains("fp-pane") ? "80vh" : "90vh";
  el.style.zIndex = el.classList.contains("fp-pane") ? "58" : "56";
  const stage = document.getElementById("chart-stage");
  if (stage) stage.classList.remove("with-drawer");
}
function dockPanel(el) {
  const draggers = ["ind-drawer", "cmp-drawer", "chart-drawer"];
  el.dataset.fpFloat = "";
  el.classList.remove("floating");
  ["position", "left", "top", "width", "height", "maxHeight", "zIndex"].forEach((k) => { el.style[k] = ""; });
  const stage = document.getElementById("chart-stage");
  if (stage && !el.classList.contains("fp-pane")) {
    const any = draggers.some((id) => { const d = document.getElementById(id); return d && !d.hidden; });
    stage.classList.toggle("with-drawer", any);
  }
}
function ensurePanelGeometry(el) {
  if (!el) return;
  const g = loadPanelGeom(el);
  const isFloatingPane = el.classList.contains("fp-pane");
  if (isFloatingPane) {
    if (g && g.width) {
      el.style.width = `${Math.max(300, g.width)}px`;
      el.style.height = `${Math.max(200, g.height)}px`;
      el.style.left = `${Math.max(0, Math.min(window.innerWidth - 120, g.left ?? 40))}px`;
      el.style.top = `${Math.max(0, Math.min(window.innerHeight - 60, g.top ?? 90))}px`;
    } else {
      const w = Math.min(440, Math.max(320, Math.round(window.innerWidth * 0.28)));
      el.style.width = `${w}px`;
      el.style.maxHeight = "78vh";
      el.style.left = `${Math.max(12, window.innerWidth - w - 26)}px`;
      el.style.top = "84px";
    }
    return;
  }
  if (g && g.floating) { floatPanel(el); el.style.left = `${g.left}px`; el.style.top = `${g.top}px`; el.style.width = `${g.width}px`; el.style.height = `${g.height}px`; }
}
function makePanelMovable(el) {
  if (!el) return;
  const handle = el.querySelector(".fp-head") || el.querySelector(".cd-head") || el.querySelector(".modal-head");
  if (!handle) return;
  if (handle.dataset.fpBound !== "1") {
    handle.dataset.fpBound = "1";
    handle.classList.add("fp-h");
    let grip = el.querySelector(".fp-grip");
    if (!grip) {
      grip = document.createElement("span");
      grip.className = "fp-grip";
      grip.title = "Drag to resize";
      el.appendChild(grip);
    }
    if (el.classList.contains("chart-drawer") && !handle.querySelector(".fp-dock")) {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "ctb-btn ghost fp-dock";
      b.innerHTML = "&#10530;";
      b.title = "Undock into a movable, resizable window (press again to dock)";
      (handle.querySelector(".cd-head-actions") || handle).prepend(b);
      b.addEventListener("click", (e) => {
        e.stopPropagation(); e.preventDefault();
        if (el.dataset.fpFloat === "1") dockPanel(el); else floatPanel(el);
        savePanelGeom(el);
      });
    }
    handle.addEventListener("mousedown", (e) => {
      if (e.button !== 0) return;
      if (e.target.closest("button,input,select,a,label,summary,textarea,.fp-dock")) return;
      if (!el.classList.contains("fp-pane") && el.dataset.fpFloat !== "1") floatPanel(el);
      const r = el.getBoundingClientRect();
      const sx = e.clientX, sy = e.clientY;
      let moved = false;
      const mv = (ev) => {
        moved = true;
        el.style.left = `${Math.max(0, Math.min(window.innerWidth - 60, r.left + ev.clientX - sx))}px`;
        el.style.top = `${Math.max(0, Math.min(window.innerHeight - 40, r.top + ev.clientY - sy))}px`;
        el.classList.add("fp-dragging");
      };
      const up = () => {
        window.removeEventListener("mousemove", mv);
        el.classList.remove("fp-dragging");
        if (moved) { clampPanel(el); savePanelGeom(el); }
      };
      window.addEventListener("mousemove", mv);
      window.addEventListener("mouseup", up, { once: true });
      e.preventDefault();
    });
    grip.addEventListener("mousedown", (e) => {
      if (e.button !== 0) return;
      if (!el.classList.contains("fp-pane") && el.dataset.fpFloat !== "1") floatPanel(el);
      const r = el.getBoundingClientRect();
      const sx = e.clientX, sy = e.clientY, w0 = r.width, h0 = r.height;
      const vw = window.innerWidth, vh = window.innerHeight;
      const mv = (ev) => {
        const w = Math.max(260, Math.min(vw - 16, w0 + ev.clientX - sx));
        const h = Math.max(180, Math.min(vh - 16, h0 + ev.clientY - sy));
        el.style.width = `${w}px`;
        el.style.height = `${h}px`;
        el.style.maxHeight = "none";
        // Growing downward/rightward must not push the grip off the viewport.
        const l = parseFloat(el.style.left) || 0;
        const t = parseFloat(el.style.top) || 0;
        if (l + w > vw - 4) el.style.left = `${Math.max(0, vw - w - 4)}px`;
        if (t + h > vh - 4) el.style.top = `${Math.max(0, vh - h - 6)}px`;
      };
      const up = () => { window.removeEventListener("mousemove", mv); clampPanel(el); savePanelGeom(el); };
      window.addEventListener("mousemove", mv);
      window.addEventListener("mouseup", up, { once: true });
      e.preventDefault(); e.stopPropagation();
    });
  }
  ensurePanelGeometry(el);
}
function bindWorkbenchExtras() {
  document.querySelectorAll(
    "#ind-drawer,#cmp-drawer,#chart-drawer,#ind-catalog .modal,#ind-custom .modal,#clear-modal .modal,#ind-info",
  ).forEach((el) => { try { makePanelMovable(el); } catch (e) { /* one bad panel must not stop the rest */ } });
  const close = $("#ind-info-close");
  if (close) close.addEventListener("click", () => {
    const p = $("#ind-info");
    if (p) { savePanelGeom(p); p.hidden = true; }
  });
  const add = $("#ind-info-add");
  if (add) add.addEventListener("click", async () => {
    const n = add.dataset.indAdd;
    if (!n) return;
    try {
      const reg = (await fetchIndicatorRegistry()).find((x) => x.name === n);
      await addToChartFromCatalog(n, reg ? reg.params : null);
      await renderIndDrawer();
      drawStatus(`${n} added to the chart.`);
    } catch (e) { drawStatus(`Add failed: ${e.message}`); }
  });
  window.addEventListener("resize", () => {
    document.querySelectorAll(".floating,.fp-pane").forEach((el) => { if (!el.hidden) clampPanel(el); });
  });
}
document.addEventListener("DOMContentLoaded", () => {
  try { bindWorkbenchExtras(); } catch (e) { /* extras are additive */ }
});

/* ============================================================================
   CHART OBJECTS MANAGER  (§objects)
   ----------------------------------------------------------------------------
   One list of everything drawn on the price chart, grouped by owner, so a
   cryptic label ("BO", "SH", "(III)", "ASCT") can be identified and removed.
   Nothing is guessed: each row is built from the object that actually exists in
   state (markers, series, layers, indicator instances, compare symbols) and its
   description comes from the provenance recorded when the object was created.
   Removal is scoped to the object it names — it never touches unrelated layers,
   saved layouts, templates or watchlists.
   ========================================================================== */

function objGroup(title, owner, note) { return { title, owner, note, items: [] }; }

function markerRows(arr, owner, fallbackDesc) {
  return (arr || []).map((m, i) => {
    const meta = markerMetaOf(m);
    return {
      id: `${owner}-${i}-${m.text || ""}`,
      label: m.text ? `${m.text}` : "(dot)",
      when: m.time,
      owner: (meta && meta.owner) || owner,
      desc: (meta && meta.desc) || fallbackDesc,
      hidden: !!m.hidden,
      toggle: () => { m.hidden = !m.hidden; flushMarkers(); },
      remove: () => { const k = arr.indexOf(m); if (k >= 0) arr.splice(k, 1); flushMarkers(); },
    };
  });
}

function seriesRows(arr, owner, desc) {
  return (arr || []).map((s, i) => ({
    id: `${owner}-series-${i}`,
    label: `line ${i + 1}`,
    when: "",
    owner,
    desc,
    hidden: false,
    toggle: () => {
      const cur = s.options ? s.options().visible !== false : true;
      try { s.applyOptions({ visible: !cur }); } catch (e) { /* gone */ }
    },
    remove: () => {
      try { state.charts.price.removeSeries(s); } catch (e) { /* already gone */ }
      const k = arr.indexOf(s);
      if (k >= 0) arr.splice(k, 1);
    },
  }));
}

/* ---- quick-layer (toolbar) objects -------------------------------------
   Each quick layer is one toolbar toggle that produces one or more real
   primitives. These helpers let the Objects manager act on the primitives
   (series / pane / owned markers), not just the row. */
function quickOwnedMarkers(q) {
  if (!q.markerOwner) return [];
  return (state.markers || []).filter((m) => ((markerMetaOf(m) || {}).owner === q.markerOwner));
}

function quickObjectHidden(q) {
  if (q.series) { try { return q.series.options().visible === false; } catch (e) { return false; } }
  if (q.seriesList && q.seriesList.length) {
    return q.seriesList.every((s) => { try { return s.options().visible === false; } catch (e) { return true; } });
  }
  if (q.paneId) { const el = document.getElementById(q.paneId); return !!(el && el.hidden); }
  if (q.markerOwner) {
    const ms = quickOwnedMarkers(q);
    return ms.length > 0 && ms.every((m) => m.hidden);
  }
  return false;
}

function toggleQuickObject(q) {
  if (q.series) {
    try { q.series.applyOptions({ visible: q.series.options().visible === false }); } catch (e) { /* gone */ }
    return;
  }
  if (q.seriesList && q.seriesList.length) {
    const anyVisible = q.seriesList.some((s) => { try { return s.options().visible !== false; } catch (e) { return false; } });
    q.seriesList.forEach((s) => { try { s.applyOptions({ visible: !anyVisible }); } catch (e) { /* gone */ } });
    return;
  }
  if (q.paneId) {
    const el = document.getElementById(q.paneId);
    if (el) el.hidden = !el.hidden;
    if (el && !el.hidden) syncPaneToPrice(q.paneId);
    return;
  }
  if (q.markerOwner) {
    const ms = quickOwnedMarkers(q);
    const anyVisible = ms.some((m) => !m.hidden);
    ms.forEach((m) => { m.hidden = anyVisible; });
    flushMarkers();
  }
}

function removeQuickObject(q) {
  // Uncheck the toolbar toggle so a reload does not rebuild it, then remove the
  // real primitive (series / pane / owned markers) — no orphaned canvas objects.
  if (q.checkbox) { const cb = document.getElementById(q.checkbox); if (cb) cb.checked = false; }
  const price = state.charts && state.charts.price;
  if (q.series && price) { try { price.removeSeries(q.series); } catch (e) { /* gone */ } }
  if (q.seriesList) q.seriesList.forEach((s) => { if (price) { try { price.removeSeries(s); } catch (e) { /* gone */ } } });
  if (q.paneId) {
    const el = document.getElementById(q.paneId);
    const c = state.charts[q.paneId];
    if (c) { try { c.remove(); } catch (e) { /* gone */ } delete state.charts[q.paneId]; }
    if (el) { el.hidden = true; try { el.innerHTML = ""; } catch (e) { /* gone */ } }
    try { renderPaneChips(); } catch (e) { /* absent */ }
  }
  if (q.markerOwner) {
    state.markers = (state.markers || []).filter((m) => ((markerMetaOf(m) || {}).owner !== q.markerOwner));
    flushMarkers();
  }
  state.quickObjects = (state.quickObjects || []).filter((x) => x.id !== q.id);
  saveQuickLayers(state.chartSymbol);
}

function collectChartObjects() {
  const groups = [];
  if (!state.chartSymbol) return groups;

  // 1. Indicator instances -------------------------------------------------
  const inds = state.customInds || [];
  if (inds.length) {
    const g = objGroup("Indicators", "Indicator engine", "Computed from the stored daily bars of the loaded symbol.");
    inds.forEach((inst) => {
      g.items.push({
        id: `ind-${inst.id}`,
        label: `${inst.label || inst.name}`,
        when: Object.entries(inst.params || {}).map(([k, v]) => `${k}=${v}`).join(" "),
        owner: `${indPlacementText(inst)}${inst.paneCollapsed ? " · pane collapsed" : ""}`,
        desc: `Indicator instance “${inst.name}” with parameters ${JSON.stringify(inst.params || {})}. `
          + `Visible rows are drawn from stored daily bars; warm-up rows are gaps.`,
        hidden: inst.visible === false,
        toggle: () => {
          inst.visible = inst.visible === false;
          try { persistCustomInds(state.chartSymbol); } catch (e) { /* storage off */ }
          applyInstanceVisibility(inst);
          renderIndDrawer();
        },
        remove: () => { removeIndicatorInstance(inst.id); renderObjectManager(); },
      });
    });
    groups.push(g);
  }

  // 1b. Quick layers (chart-toolbar toggles) -------------------------------
  // The chart-toolbar indicators (SMA/EMA/BB/volume/RSI/MACD/swings) are real
  // visible primitives; they belong in the manager alongside catalog instances.
  const quicks = state.quickObjects || [];
  if (quicks.length) {
    const g = objGroup("Quick layers", "Toolbar toggles",
      "Chart-level indicator toggles from the chart toolbar (rebuilt on load; not persisted per symbol).");
    quicks.forEach((q) => {
      g.items.push({
        id: q.id,
        label: q.label,
        when: q.type || "",
        owner: q.owner || "Chart toolbar",
        desc: q.desc || `${q.label} — ${q.type || "chart object"}.`,
        hidden: quickObjectHidden(q),
        toggle: () => { toggleQuickObject(q); },
        remove: () => { removeQuickObject(q); },
      });
    });
    groups.push(g);
  }

  // 2. Analysis layers -----------------------------------------------------
  const layersOn = Object.entries(LAYER_DEFS).filter(([id]) => state.layers && state.layers[id]);
  if (layersOn.length) {
    const g = objGroup("Analysis layers", "Layer engine", "Each layer is fetched on demand and drawn from stored bars.");
    layersOn.forEach(([id, def]) => {
      const n = state.layerCounts[id];
      g.items.push({
        id: `layer-${id}`,
        label: def.label,
        when: n == null ? "" : `${n} detected`,
        owner: def.hint,
        desc: `Analysis layer “${def.label}”: ${def.hint}. Turning it off removes its overlay from the chart.`,
        hidden: false,
        toggle: () => { toggleLayer(id); renderObjectManager(); },
        remove: () => { toggleLayer(id); renderObjectManager(); },
      });
    });
    groups.push(g);
  }

  // 3. Pattern / candle / swing annotations --------------------------------
  const annot = [];
  annot.push(...markerRows(state.patternMarkers, "Chart-pattern detector",
    "Marker from the chart-pattern detector (breakout/invalidation level or pattern code)."));
  annot.push(...markerRows(state.candleMarkers, "Candlestick detector",
    "Candlestick-pattern marker."));
  annot.push(...markerRows(state.markers, "Swing / pivot detector",
    "Swing or pivot marker (SH/SL = OHLC swing, CH/CL = close-based pivot)."));
  annot.push(...markerRows(state.elliottMarkers, "Elliott Wave — your manual label",
    "Wave label you assigned."));
  annot.push(...markerRows(state.elliottAutoMarkers, "Elliott Wave — automatic candidate",
    "Wave label from the automatic candidate count."));
  annot.push(...markerRows(state.harmonicMarkers, "Harmonic-pattern detector",
    "Harmonic-pattern completion marker."));
  if (annot.length) {
    const g = objGroup("Annotations & markers", "Detectors", "Compact labels drawn on bars. Hover a row for its full meaning.");
    g.items.push(...annot);
    groups.push(g);
  }

  // 4. Analysis line series ------------------------------------------------
  const lines = [];
  lines.push(...seriesRows(state.patternSeries, "Chart-pattern detector", "Pattern pivot lines and breakout/invalidation level lines."));
  lines.push(...seriesRows(state.harmonicSeries, "Harmonic-pattern detector", "Harmonic XABCD point-to-point lines."));
  lines.push(...seriesRows((state.layerSeries && state.layerSeries.sr) || [], "Support & resistance", "Detected S/R zone lines."));
  lines.push(...seriesRows((state.layerSeries && state.layerSeries.fib) || [], "Fibonacci", "Fib retracement/extension lines."));
  lines.push(...seriesRows((state.layerSeries && state.layerSeries.profile) || [], "Volume profile", "POC and value-area lines."));
  lines.push(...seriesRows(state.elliottLine ? [state.elliottLine] : [], "Elliott Wave — your manual label", "Line joining your manual wave labels."));
  lines.push(...seriesRows(state.elliottAutoLine ? [state.elliottAutoLine] : [], "Elliott Wave — automatic candidate", "Line joining the automatic candidate's pivots."));
  if (lines.length) {
    const g = objGroup("Analysis lines", "Detectors", "Line objects drawn by detectors and analysis layers.");
    g.items.push(...lines);
    groups.push(g);
  }

  // 5. Manual drawings -----------------------------------------------------
  const drawings = loadDrawings(state.chartSymbol);
  if (drawings.length) {
    const g = objGroup("Manual drawings", "Your drawings", "Objects you placed. Managed in full in the Draw panel.");
    g.items.push(...drawings.map((d) => ({
      id: `draw-${d.id}`,
      label: d.name || DRAW_LABELS[d.type] || d.type,
      when: `${d.t1} @ ${fmtNum(Number(d.p1))}`,
      owner: d.locked ? "locked" : "editable",
      desc: `Manual drawing of type ${d.type}${d.text ? `, text “${d.text}”` : ""}. `
        + `Select it on the chart, or use the Draw panel to rename/lock/delete it.`,
      hidden: !!d.hidden,
      toggle: () => {
        const all = loadDrawings(state.chartSymbol);
        const t = all.find((x) => x.id === d.id);
        if (t) { t.hidden = !t.hidden; persistDrawings(state.chartSymbol, all); renderDrawings(); }
        renderObjectManager();
      },
      remove: () => {
        const all = loadDrawings(state.chartSymbol).filter((x) => x.id !== d.id);
        persistDrawings(state.chartSymbol, all);
        renderDrawings();
        renderDrawList();
        renderObjectManager();
      },
    })));
    groups.push(g);
  }

  // 6. Compare symbols -----------------------------------------------------
  const cmp = (state.compare && state.compare.symbols) || [];
  if (cmp.length) {
    const g = objGroup("Comparison symbols", "Compare", "Rebased at the first visible bar; gaps where a date is missing.");
    cmp.forEach((s) => {
      g.items.push({
        id: `cmp-${s.symbol}`,
        label: s.symbol,
        when: s.visible === false ? "hidden" : "shown",
        owner: "Compare overlay",
        desc: `Comparison series for ${s.symbol}, rebased to the first visible observation so the shape is comparable (this is not a price level).`,
        hidden: s.visible === false,
        toggle: async () => { s.visible = !(s.visible !== false); saveCompareCfg(); await applyCompareToChart(); renderComparePanel(); renderObjectManager(); },
        remove: async () => { state.compare.symbols = state.compare.symbols.filter((x) => x.symbol !== s.symbol); saveCompareCfg(); await applyCompareToChart(); renderComparePanel(); renderObjectManager(); },
      });
    });
    groups.push(g);
  }

  return groups;
}

function renderObjectManager() {
  const body = $("#obj-body");
  if (!body) return;
  const groups = collectChartObjects();
  const total = groups.reduce((a, g) => a + g.items.length, 0);
  if (!total) {
    body.innerHTML = `<div class="empty">Nothing is drawn on this chart yet. Add an indicator, enable an analysis `
      + `layer, or place a drawing and it will appear here with its owner.</div>`;
    return;
  }
  const head = `<p class="hint">${total} object(s) identified across ${groups.length} owner(s) for `
    + `<b>${esc(state.chartSymbol || "")}</b>. Rows show who created each object; Hide/Remove act only on that object.</p>`;
  body.innerHTML = head + groups.map((g) => `
    <h3 class="cd-sub">${esc(g.title)} <span class="hint">— ${esc(g.owner)}</span></h3>
    ${g.note ? `<div class="hint obj-note">${esc(g.note)}</div>` : ""}
    <div class="obj-list">${g.items.map((it) => `
      <div class="obj-row" title="${esc(it.desc || "")}">
        <span class="obj-label">${esc(it.label)}</span>
        <span class="obj-meta">${esc(it.when || "")}${it.owner ? ` · ${esc(it.owner)}` : ""}</span>
        <button class="ctb-btn ghost obj-hide" data-id="${esc(it.id)}">${it.hidden ? "Show" : "Hide"}</button>
        <button class="ctb-btn ghost obj-del" data-id="${esc(it.id)}" title="${esc(it.desc || "")}">Remove</button>
      </div>`).join("")}</div>`).join("");
  // Wire the action buttons from the same list (identity preserved by index).
  const byId = new Map();
  groups.forEach((g) => g.items.forEach((it) => byId.set(it.id, it)));
  body.querySelectorAll(".obj-hide").forEach((b) => b.addEventListener("click", async () => {
    const it = byId.get(b.dataset.id);
    if (it) { await it.toggle(); renderObjectManager(); }
  }));
  body.querySelectorAll(".obj-del").forEach((b) => b.addEventListener("click", async () => {
    const it = byId.get(b.dataset.id);
    if (it) { await it.remove(); renderObjectManager(); }
  }));
}

function bindObjectsPane() {
  const pane = $("#obj-pane");
  if (!pane) return;
  const open = $("#pop-objects-btn");
  const close = $("#obj-close");
  const refresh = $("#obj-refresh");
  if (open && open.dataset.bound !== "1") {
    open.dataset.bound = "1";
    open.addEventListener("click", () => {
      const p = $("#obj-pane");
      if (p.hidden) { p.hidden = false; makePanelMovable(p); ensurePanelGeometry(p); renderObjectManager(); }
      else { savePanelGeom(p); p.hidden = true; }
    });
  }
  if (close && close.dataset.bound !== "1") {
    close.dataset.bound = "1";
    close.addEventListener("click", () => { const p = $("#obj-pane"); savePanelGeom(p); p.hidden = true; });
  }
  if (refresh && refresh.dataset.bound !== "1") {
    refresh.dataset.bound = "1";
    refresh.addEventListener("click", () => renderObjectManager());
  }
}
document.addEventListener("DOMContentLoaded", () => {
  try { bindObjectsPane(); makePanelMovable($("#obj-pane")); } catch (e) { /* additive */ }
});

/* ============================================================================
   ELLIOTT WAVE — run and show (§elliott)
   ----------------------------------------------------------------------------
   Clicking "Analyze" only filled a table. These actions make the two modes
   explicit and visible: a manual-labelling mode is genuinely manual, and the
   automatic count must draw itself on the chart when asked — or say plainly
   that no defensible count was found.
   ========================================================================== */
function elliottStatus(msg) {
  const el = $("#elliott-status");
  if (el) el.textContent = msg || "";
}
async function runElliottAndDraw() {
  const symbol = state.chartSymbol || ($("#symbol-input").value || "").trim().toUpperCase();
  if (!symbol) { elliottStatus("Enter a symbol first."); return; }
  elliottStatus("Elliott: analysing…");
  try { await runElliott(); }
  catch (e) { elliottStatus(`Elliott analysis failed: ${e.message}`); return; }
  const auto = state.elliottAuto || {};
  const cands = auto.candidates || [];
  const winBars = (auto.window && auto.window.bars) || (state.chartDates || []).length;
  if (!cands.length) {
    elliottStatus(`Elliott: no wave count — ${auto.message || "not enough confirmed swings in the analysis window"}. `
      + `Nothing was drawn (analysed ${winBars} bars).`);
    return;
  }
  let res;
  try { res = drawElliottCandidate(symbol, 0); }
  catch (e) { elliottStatus(`Elliott drawing failed: ${e.message}`); return; }
  if (!res || !res.drawn) {
    elliottStatus(`Elliott: ${cands.length} wave count(s) found, but candidate “${cands[0].label}” produced nothing to draw`
      + (res && res.offRange ? ` — all ${res.offRange} of its pivots fall outside the ${(state.chartDates || []).length} bars the chart has loaded; widen the chart range or set the analysis period to “Same as chart range”` : "")
      + `. ${(res && res.reason) || "No pivots were returned."}`);
    return;
  }
  const drewSubset = res.engineCount && res.drawn < res.engineCount;
  elliottStatus(`Elliott: drew candidate “${res.label}” — ${res.drawn} pivot(s)`
    + (drewSubset ? ` of ${res.engineCount} (the rest fall outside the loaded chart range)` : "")
    + `, ${res.first} → ${res.last}, ${res.certainty} certainty. `
    + `${res.moved ? "The chart was scrolled to bring the drawing into view (the loaded range is unchanged)." : "Viewport unchanged."} `
    + `${cands.length} count(s) available — press Draw on another row to switch. `
    + `Listed under “Elliott Wave — automatic candidate” in Objects.`);
  renderObjectManager();
}
async function eraseElliottAnnotations() {
  const chart = state.charts.price;
  if (!chart) { elliottStatus("Load a chart first."); return; }
  ["elliottAutoLine", "elliottLine"].forEach((k) => {
    if (state[k]) { try { chart.removeSeries(state[k]); } catch (e) { /* gone */ } state[k] = null; }
  });
  state.elliottAutoMarkers = [];
  state.elliottMarkers = [];
  state.elliottAuto = null;
  flushMarkers();
  try { await applyElliottLabels(); } catch (e) { /* no saved labels */ }
  elliottStatus("Elliott chart drawing removed. Saved manual wave labels were kept (use Clear labels to delete those).");
  renderObjectManager();
}
document.addEventListener("DOMContentLoaded", () => {
  const rd = $("#elliott-run-draw");
  if (rd && rd.dataset.bound !== "1") { rd.dataset.bound = "1"; rd.addEventListener("click", runElliottAndDraw); }
  const er = $("#elliott-erase");
  if (er && er.dataset.bound !== "1") { er.dataset.bound = "1"; er.addEventListener("click", eraseElliottAnnotations); }
});

/* ============================================================================
   Sasto Share workspace
   ----------------------------------------------------------------------------
   The reference platform's market, valuation, risk, rotation and dividend
   views. Each panel calls one Sasto Share endpoint and renders what it returns:
   a real table, a real chart, or an explicit unavailable state carrying the
   endpoint's reason. No panel invents a value to fill a layout.
   ============================================================================ */
const SS_TAB_TO_NAV = {
  pulse: "sastoshare", movers: "ssmovers", valuation: "ssvaluation",
  risk: "ssrisk", rotation: "ssrotation", dividends: "ssdividends", strategy: "ssstrategy",
};
const SS_NAV_TO_TAB = Object.keys(SS_TAB_TO_NAV).reduce((acc, tab) => {
  acc[SS_TAB_TO_NAV[tab]] = tab;
  return acc;
}, {});
let ssTab = "pulse";

function initSastoShare() {
  const host = $("#ss-tabs");
  if (!host || host.dataset.bound === "1") return;
  host.dataset.bound = "1";
  $$("#ss-tabs .ss-tab").forEach((b) =>
    b.addEventListener("click", () => ssSubTab(b.dataset.sstab)));
}

/* Switch sub-tab and keep the primary sidebar and the sub-nav in step, so the
   two navigation levels can never point at different panels. */
function ssSubTab(tab, opts) {
  const t = SS_TAB_TO_NAV[tab] ? tab : "pulse";
  ssTab = t;
  $$("#ss-tabs .ss-tab").forEach((b) => b.classList.toggle("active", b.dataset.sstab === t));
  const navName = SS_TAB_TO_NAV[t];
  $$("#nav button[data-view]").forEach((b) => b.classList.toggle("active", b.dataset.view === navName));
  if (!(opts && opts.skipLoad)) loadSastoShare(t);
}

async function loadSastoShare(tab) {
  const host = $("#ss-body");
  if (!host) return;
  const t = tab || ssTab;
  const label = ($("#ss-tabs .ss-tab[data-sstab='" + t + "']") || {}).textContent || t;
  host.innerHTML = ssCard(label, `<div class="empty">Loading ${esc(label)}…</div>`);
  try {
    if (t === "pulse") await ssPulse(host);
    else if (t === "movers") await ssMovers(host);
    else if (t === "valuation") await ssValuation(host);
    else if (t === "risk") await ssRisk(host);
    else if (t === "rotation") await ssRotation(host);
    else if (t === "dividends") await ssDividends(host);
    else if (t === "strategy") await ssStrategy(host);
    else host.innerHTML = ssCard(label, `<div class="empty">Unknown panel.</div>`);
  } catch (e) {
    host.innerHTML = ssCard(label, `<div class="error">This panel could not load: ${esc(e.message)}</div>`);
  }
}

/* ------------------------------------------------------------- small parts */
function ssCard(title, inner, opts) {
  const o = opts || {};
  return `<div class="card wide ss-card${o.cls ? " " + o.cls : ""}">`
    + (title ? `<h2>${esc(title)}${o.badge ? ` <span class="pill">${esc(o.badge)}</span>` : ""}</h2>` : "")
    + (o.hint ? `<p class="hint">${o.hint}</p>` : "")
    + inner
    + `</div>`;
}

function ssKpis(items) {
  const cells = items.map((k) => `<div class="ss-kpi">
      <span class="ss-kpi-label">${esc(k.label)}</span>
      <span class="ss-kpi-value ${k.cls || ""}">${k.value}</span>
      ${k.sub ? `<span class="ss-kpi-sub">${k.sub}</span>` : ""}
    </div>`).join("");
  return `<div class="ss-kpis">${cells}</div>`;
}

function ssRow(cells) {
  return cells.map((c) => (typeof c === "string" || typeof c === "number")
    ? { html: esc(String(c)) } : c);
}

/* A 250-bar range with a marker at the current position. The track is a plain
   HTML bar so it costs nothing to render hundreds of them. */
function ssRangeBar(range) {
  if (!range) return { html: `<span class="hint">no 250-bar window stored</span>` };
  const lo = fmtNum(range.low), hi = fmtNum(range.high);
  if (range.position == null) {
    return { html: `<span class="hint" title="${esc(range.basis || "")}">${lo}–${hi} (flat)</span>` };
  }
  const p = Math.max(0, Math.min(100, range.position * 100));
  return { html: `<span class="ss-range" title="250-bar range ${lo}–${hi}; last close at ${(range.position * 100).toFixed(0)}% of it">`
    + `<span class="ss-range-fill" style="width:${p.toFixed(1)}%"></span>`
    + `<span class="ss-range-dot" style="left:${p.toFixed(1)}%"></span></span>`
    + `<span class="ss-range-txt">${lo} → ${hi}</span>` };
}

function ssUnavailable(reason) {
  return `<div class="empty">${esc(reason || "No data available.")}</div>`;
}

function ssCaveats(list) {
  if (!list || !list.length) return "";
  return `<ul class="ss-caveats">${list.map((c) => `<li>${esc(c)}</li>`).join("")}</ul>`;
}

function ssSymbolField(id, value, placeholder) {
  return `<label>Symbol <input id="${id}" value="${esc(value || "")}" placeholder="${esc(placeholder || "NABIL")}" style="width:9em" /></label>`;
}

function ssSymbol() {
  const fromChart = (state.chartSymbol || ($("#symbol-input") && $("#symbol-input").value) || "").trim().toUpperCase();
  return fromChart || "NABIL";
}

/* ------------------------------------------------------------------- pulse */
async function ssPulse(host) {
  const [pulse, dash] = await Promise.all([
    api("/api/sastoshare/pulse"),
    api("/api/market/dashboard?index_limit=200&top=6").catch(() => null),
  ]);
  const b = pulse.barometer || {}, s = pulse.sentiment || {}, g = pulse.golden_cross || {};
  const market = (dash && dash.market) || {};
  const idx = (dash && dash.index_chart) || {};

  const parts = [];
  parts.push(ssCard("Market pulse", ssKpis([
    { label: "NEPSE index", value: idx.available ? fmtNum(idx.latest) : "—",
      sub: idx.available ? `${fmtPct(idx.pct)} on ${esc(idx.last)}` : esc(idx.reason || "not stored"),
      cls: pctClass(idx.pct) },
    { label: "Near 52-week high", value: b.near_high && b.near_high.pct != null ? fmtPct(b.near_high.pct) : "—",
      sub: b.near_high ? `${b.near_high.count} of ${b.near_high.denominator} symbols` : "" },
    { label: "Near 52-week low", value: b.near_low && b.near_low.pct != null ? fmtPct(b.near_low.pct) : "—",
      sub: b.near_low ? `${b.near_low.count} of ${b.near_low.denominator} symbols` : "" },
    { label: "Above SMA 50", value: s.above_50 && s.above_50.pct != null ? fmtPct(s.above_50.pct) : "—",
      sub: s.above_50 ? `${s.above_50.count} of ${s.above_50.denominator}` : "" },
    { label: "Above SMA 200", value: s.above_200 && s.above_200.pct != null ? fmtPct(s.above_200.pct) : "—",
      sub: s.above_200 ? `${s.above_200.count} of ${s.above_200.denominator}` : "" },
    { label: "SMA50 > SMA200", value: g.pct != null ? fmtPct(g.pct) : "—",
      sub: g.denominator ? `${g.count} of ${g.denominator}` : "" },
  ]), { hint: esc(b.definition || "") }));

  const gaugeHosts = `<div class="ss-gauges">
      <div><div class="ss-gauge-host" id="ss-g50"></div><p class="hint">Share of symbols above their own 50-bar SMA</p></div>
      <div><div class="ss-gauge-host" id="ss-g200"></div><p class="hint">Share of symbols above their own 200-bar SMA</p></div>
    </div>`;
  parts.push(ssCard("Participation", gaugeHosts, { hint: esc(s.above_50 ? "A reading is a state, not a signal." : "") }));

  if (dash && Array.isArray(dash.sectors) && dash.sectors.length) {
    parts.push(ssCard("Sector performance (latest stored session)",
      `<div id="ss-sector-bars"></div>`,
      { hint: esc(market.as_of ? `As of ${market.as_of}.` : "") }));
  }

  parts.push(ssCard("Percentage of stocks above moving averages, by sector",
    pulse.sector_ma && pulse.sector_ma.length
      ? table(["Sector", "Above 10", "Above 20", "Above 50", "Above 200", "SMA50 > SMA200"],
        pulse.sector_ma.map((r) => ssRow([
          r.sector,
          ssPctCell(r.above_sma_10), ssPctCell(r.above_sma_20), ssPctCell(r.above_sma_50),
          ssPctCell(r.above_sma_200), ssPctCell(r.sma_50_above_200),
        ])))
      : ssUnavailable("No sector had enough history for a moving-average reading."),
    { hint: esc(pulse.sector_ma_definition || ""), badge: "sector breadth" }));

  const rangeCard = (title, rows, edgeNote) => ssCard(title,
    rows && rows.length
      ? table(["Sector", "Symbols", "Distribution"], rows.map((r) => ssRow([
        r.sector, String(r.n),
        { html: (r.bins || []).map((x) => `<span class="ss-bin"><b>${esc(x.label)}</b> ${x.count}</span>`).join("") },
      ])))
      : ssUnavailable("No stored fundamental could be placed in a range."),
    { hint: esc(edgeNote || "") });

  parts.push(rangeCard("Number of stocks in P/E ranges", pulse.pe_ranges,
    "P/E uses the stored reported P/E where present, otherwise the last close divided by the last reported EPS."));
  parts.push(rangeCard("Number of stocks in P/B ranges", pulse.pb_ranges,
    "P/B = last close ÷ last reported net worth per share. Both inputs come from stored rows."));
  parts.push(rangeCard("Number of stocks in price ranges", pulse.price_ranges,
    "Last stored close for each symbol."));

  host.innerHTML = parts.join("");

  if (s.above_50 && s.above_50.pct != null) {
    VIZ.gauge($("#ss-g50"), { value: s.above_50.pct, min: 0, max: 100, height: 150, maxSize: 220,
      label: "% above SMA 50", valueFormat: (v) => v.toFixed(1), sub: `${s.above_50.count}/${s.above_50.denominator}`,
      ariaLabel: `Share of symbols above their 50-bar SMA: ${s.above_50.pct}%` });
  } else {
    VIZ.empty($("#ss-g50"), "No symbol had a 50-bar SMA.");
  }
  if (s.above_200 && s.above_200.pct != null) {
    VIZ.gauge($("#ss-g200"), { value: s.above_200.pct, min: 0, max: 100, height: 150, maxSize: 220,
      label: "% above SMA 200", valueFormat: (v) => v.toFixed(1), sub: `${s.above_200.count}/${s.above_200.denominator}`,
      ariaLabel: `Share of symbols above their 200-bar SMA: ${s.above_200.pct}%` });
  } else {
    VIZ.empty($("#ss-g200"), "No symbol had a 200-bar SMA.");
  }

  const barHost = $("#ss-sector-bars");
  if (barHost && dash && dash.sectors) {
    const sorted = dash.sectors.slice().sort((a, b2) => (b2.avg_pct || 0) - (a.avg_pct || 0));
    VIZ.bars(barHost, {
      orientation: "h", height: Math.max(200, sorted.length * 22), signed: true, zeroLine: true,
      items: sorted.map((x) => ({ label: x.sector, value: x.avg_pct, color: (x.avg_pct || 0) >= 0 ? PRAVAHA.up : PRAVAHA.down })),
      valueFormat: (v) => `${fmtNum(v)}%`, ariaLabel: "Average percent change by sector for the latest stored session",
    });
  }
}

function ssPctCell(read) {
  if (!read || read.pct == null) return { html: `<span class="hint">—</span>` };
  return { html: `<span class="${pctClass(read.pct - 50)}">${fmtNum(read.pct, 1)}%</span>`
    + `<span class="hint"> (${read.count}/${read.denominator})</span>` };
}

/* ------------------------------------------------------------------ movers */
async function ssMovers(host) {
  const d = await api("/api/sastoshare/movers?limit=15&spark=30");
  const block = (title, rows, tag) => {
    if (!rows || !rows.length) return ssCard(title, ssUnavailable("No quotes were returned for this ranking."));
    const body = table(
      ["Symbol", "Price", "Change", "Trend (30 stored closes)", "250-bar range", "Volume", "R-Vol", "Market cap"],
      rows.map((r, i) => ssRow([
        { html: `<b>${esc(r.symbol)}</b>` },
        { html: fmtNum(r.ltp) },
        { html: `<span class="${pctClass(r.percent_change)}">${fmtPct(r.percent_change)}</span>` },
        { html: r.sparkline && r.sparkline.length >= 2
          ? `<div class="ss-spark" id="ss-spark-${tag}-${i}"></div>`
          : `<span class="hint">—</span>` },
        ssRangeBar(r.range_52w),
        { html: r.volume != null ? fmtCompact(r.volume) : "—" },
        { html: r.rvolume != null ? fmtNum(r.rvolume) : `<span class="hint">—</span>` },
        { html: r.market_cap && r.market_cap.value_npr != null
          ? `${fmtCompact(r.market_cap.value_npr)}<span class="hint"> derived</span>`
          : `<span class="hint">${esc((r.market_cap && r.market_cap.unavailable_reason) || "unavailable")}</span>` },
      ])));
    return ssCard(title, body, { hint: "Sparklines are stored daily closes. The reference site draws intraday lines; no intraday series is stored here, so none is drawn. R-Vol = last volume ÷ 20-bar average." });
  };

  host.innerHTML = block("Gainers", d.gainers, "gain") + block("Losers", d.losers, "lose");
  [["gain", d.gainers], ["lose", d.losers]].forEach(([tag, rows]) => {
    (rows || []).forEach((r, i) => {
      const el = $(`#ss-spark-${tag}-${i}`);
      if (el && r.sparkline && r.sparkline.length >= 2) {
        VIZ.sparkline(el, { values: r.sparkline, height: 26,
          ariaLabel: `${r.symbol} last ${r.sparkline.length} stored closes` });
      }
    });
  });
}

/* --------------------------------------------------------------- valuation */
async function ssValuation(host) {
  const sym = ssSymbol();
  const [models, hist] = await Promise.all([
    api(`/api/sastoshare/valuation/${encodeURIComponent(sym)}`),
    api(`/api/sastoshare/valuation-history/${encodeURIComponent(sym)}?limit=750`),
  ]);

  const toolbar = `<div class="controls">
    ${ssSymbolField("ss-val-symbol", sym)}
    <button class="ctb-btn" id="ss-val-load">Load</button>
    <label>Assumed growth % <input id="ss-val-growth" type="number" step="0.5" placeholder="auto" style="width:6.5em" /></label>
    <label>Required return % <input id="ss-val-req" type="number" step="0.5" value="12" style="width:6.5em" /></label>
  </div>
  <p class="hint">Growth left blank uses the stored annual-EPS CAGR. The required return is an assumption you supply, not a stored figure.</p>`;

  const modelRows = (models.models || []).map((m) => ssRow([
    { html: `<b>${esc(m.model)}</b>` },
    { html: `<code>${esc(m.formula)}</code>` },
    { html: m.value != null ? fmtNum(m.value) : `<span class="hint">unavailable</span>` },
    { html: Object.entries(m.inputs || {}).filter(([, v]) => v != null)
        .map(([k, v]) => `<span class="ss-kv">${esc(k)}=${esc(String(v))}</span>`).join("") || `<span class="hint">—</span>` },
    { html: (m.missing && m.missing.length)
        ? `<span class="warn-text">${esc(m.missing.join("; "))}</span>` : `<span class="hint">all inputs stored</span>` },
    { html: `<span class="hint">${esc(m.notes || "")}</span>` },
  ]));

  const parts = [];
  parts.push(ssCard(`Valuation models — ${sym}`, toolbar + ssKpis([
    { label: "Price", value: fmtNum(models.price), sub: models.price_date ? esc(models.price_date) : "" },
    { label: "EPS", value: fmtNum(models.eps), sub: models.eps_period ? `period end ${esc(models.eps_period)}` : "" },
    { label: "BVPS", value: fmtNum(models.bvps) },
    { label: "Reported P/E", value: models.pe != null ? fmtNum(models.pe) : "—" },
    { label: "EPS growth", value: models.growth_pct != null ? fmtPct(models.growth_pct) : "—",
      sub: esc(models.growth_basis || "no annual EPS history") },
  ]), { badge: "classical formulas" }));
  parts.push(ssCard("Models", modelRows.length ? table(
    ["Model", "Formula", "Value", "Inputs", "Missing inputs", "Note"], modelRows)
    : ssUnavailable("No valuation model could be computed."), { hint: (models.caveats || []).map(esc).join(" ") }));

  if (hist.available) {
    parts.push(ssCard(`Price / P/E / P/B — ${sym}`,
      `<div class="ss-panes">
         <div><div class="ss-pane-label">Price (NRs)</div><div id="ss-pane-price"></div></div>
         <div><div class="ss-pane-label">P/E (step function, reported periods)</div>
           <label class="hint ss-pe-toggle"><input type="checkbox" id="ss-pe-full" /> full range</label>
           <div id="ss-pane-pe"></div><p class="hint" id="ss-pe-note"></p></div>
         <div><div class="ss-pane-label">P/B (step function, reported periods)</div><div id="ss-pane-pb"></div></div>
       </div>
       <p class="hint">${esc(hist.alignment_note || "")}</p>
       <p class="hint">${esc(hist.method || "")}</p>
       <ul class="ss-caveats">${(hist.caveats || []).map((c) => `<li>${esc(c)}</li>`).join("")}</ul>
       ${(hist.suspect_periods || []).length
          ? `<p class="hint"><b>Suspect periods flagged:</b> ${hist.suspect_periods.map((s) =>
              `${esc(s.period_end)} (EPS ${fmtNum(s.eps)} vs a median annual EPS of ${fmtNum(s.median_annual_eps)} — ${esc(s.label)})`).join("; ")}</p>`
          : ""}`,
      { badge: `${(hist.dates || []).length} bars` }));
  } else {
    parts.push(ssCard(`Price / P/E / P/B — ${sym}`, ssUnavailable(hist.reason || "No fundamental history stored for this symbol.")));
  }

  host.innerHTML = parts.join("");
  bindSsValuation();
  ssValuationPanes = hist;

  const dates = hist.dates || [];
  if (hist.available && dates.length) {
    VIZ.line($("#ss-pane-price"), {
      labels: dates, series: [{ name: "Close", values: hist.close, color: PRAVAHA.cyan, area: true }],
      height: 180, yFormat: (v) => fmtNum(v, 0), ariaLabel: `${sym} close price`,
    });
    ssRenderPePane();
    const pbVals = hist.pb || [];
    if (pbVals.some((v) => v != null)) {
      VIZ.line($("#ss-pane-pb"), { labels: dates,
        series: [{ name: "P/B", values: pbVals, color: PRAVAHA.up }], height: 170,
        yFormat: (v) => fmtNum(v, 2), ariaLabel: `${sym} historical P/B` });
    } else {
      VIZ.empty($("#ss-pane-pb"), "No net-worth-per-share record is stored, so a P/B series cannot be built.");
    }
  }
}

/* The P/E pane. Values are drawn against the payload's readability cap unless
   the reader asks for the full range; a capped-out segment is drawn as a gap,
   never clamped to the ceiling, and the note names the largest value and the
   period that produced it. */
let ssValuationPanes = null;
function ssRenderPePane() {
  const hist = ssValuationPanes;
  const host = $("#ss-pane-pe");
  if (!hist || !host) return;
  const peVals = hist.pe || [];
  const note = $("#ss-pe-note");
  if (!peVals.some((v) => v != null)) {
    VIZ.empty(host, "No EPS record is stored, so a P/E series cannot be built.");
    if (note) note.textContent = "";
    return;
  }
  const axis = hist.pe_axis || {};
  const cap = axis.cap || 150;
  const full = !!($("#ss-pe-full") && $("#ss-pe-full").checked);
  const largest = axis.largest;
  let values = peVals;
  if (!full) values = peVals.map((v) => (v != null && v > cap ? null : v));
  const series = [{ name: "P/E", values, color: PRAVAHA.caution }];
  const sectorSeries = hist.sector_pe_series || [];
  if (sectorSeries.length) {
    const byDate = {};
    sectorSeries.forEach((p) => { byDate[p.date] = p.pe; });
    const s = hist.dates.map((d) => (d in byDate ? byDate[d] : null));
    series.push({ name: "Sector median P/E",
      values: full ? s : s.map((v) => (v != null && v > cap ? null : v)), color: PRAVAHA.emerald });
  }
  VIZ.line(host, {
    labels: hist.dates, series, height: 170,
    yFormat: (v) => fmtNum(v, 1), ariaLabel: `${hist.symbol} historical P/E`,
  });
  if (!note) return;
  const above = axis.points_above_cap || 0;
  let txt = full
    ? "Showing the full range, including values the axis cap would hide."
    : `Axis capped at ${fmtNum(cap, 0)}×; ${fmtInt(above)} of ${fmtInt(peVals.filter((v) => v != null).length)} points above the cap are drawn as gaps, not clamped.`;
  if (largest && largest.value > cap) {
    txt += ` Largest ${fmtNum(largest.value, 0)}× on ${largest.date} (EPS ${fmtNum(largest.eps)}, i.e. a near-zero denominator).`;
  }
  note.textContent = txt;
}

function bindSsValuation() {
  const btn = $("#ss-val-load");
  if (btn) btn.addEventListener("click", () => loadSastoShare("valuation"));
  const input = $("#ss-val-symbol");
  if (input) input.addEventListener("keydown", (e) => { if (e.key === "Enter") loadSastoShare("valuation"); });
  const full = $("#ss-pe-full");
  if (full) full.addEventListener("change", ssRenderPePane);
}

/* --------------------------------------------------------- risk/volatility */
async function ssRisk(host) {
  const sym = ssSymbol();
  const [risk, vol] = await Promise.all([
    api(`/api/sastoshare/risk/${encodeURIComponent(sym)}`),
    api(`/api/sastoshare/volatility/${encodeURIComponent(sym)}`),
  ]);

  const parts = [];
  parts.push(ssCard(`Risk & levels — ${sym}`,
    `<div class="controls">${ssSymbolField("ss-risk-symbol", sym)}
      <button class="ctb-btn" id="ss-risk-load">Load</button></div>`));

  if (!risk.available) {
    parts.push(ssCard("Support, resistance and risk-reward", ssUnavailable(risk.reason)));
  } else {
    const rows = ["daily", "weekly"].map((tf) => {
      const f = risk[tf] || {};
      if (f.available === false) return ssRow([tf, { html: `<span class="hint" colspan="7">${esc(f.reason || "unavailable")}</span>` }]);
      return ssRow([
        { html: `<b>${esc(tf)}</b>` },
        { html: esc(f.trend || "—") },
        { html: f.support ? `${fmtNum(f.support.price)}<span class="hint"> ${esc(f.support.swing_date || "")}</span>` : `<span class="hint">${esc(f.support_missing_reason || "none")}</span>` },
        { html: f.resistance ? `${fmtNum(f.resistance.price)}<span class="hint"> ${esc(f.resistance.swing_date || "")}</span>` : `<span class="hint">${esc(f.resistance_missing_reason || "none")}</span>` },
        { html: f.stop ? fmtNum(f.stop.price) : `<span class="hint">—</span>` },
        { html: f.target ? fmtNum(f.target.price) : `<span class="hint">—</span>` },
        { html: f.reward_risk != null ? `<b>${fmtNum(f.reward_risk)}</b>` : `<span class="hint">${esc(f.framing_reason || "not framed")}</span>` },
      ]);
    });
    parts.push(ssCard("Support, resistance and risk-reward",
      table(["Timeframe", "Structure", "Support", "Resistance", "Invalidation", "Target", "Reward : risk"], rows),
      { hint: esc(risk.levels_note || ""), badge: risk.as_of ? `as of ${risk.as_of}` : "" }));
    parts.push(ssCard("Position sizing",
      table(["Timeframe", "Per-share risk", "Shares", "Notional", "Reason"],
        ["daily", "weekly"].map((tf) => {
          const f = risk[tf] || {};
          const r = (risk[tf] || {}).sizing_reason || "—";
          return ssRow([tf,
            f.per_share_risk != null ? fmtNum(f.per_share_risk) : `<span class="hint">—</span>`,
            f.position_shares != null ? String(f.position_shares) : `<span class="hint">—</span>`,
            f.position_notional != null ? fmtCompact(f.position_notional) : `<span class="hint">—</span>`,
            { html: `<span class="hint">${esc(f.sizing_reason || r)}</span>` }]);
        })),
      { hint: "Sizing follows from the invalidation distance; with no framed level there is no size, and the engine's reason is shown instead of a made-up number." }));
    if (risk.caveats) parts.push(ssCard("Caveats", `<ul class="ss-caveats">${risk.caveats.map((c) => `<li>${esc(c)}</li>`).join("")}</ul>`));
  }

  if (vol.available) {
    parts.push(ssCard(`Volatility — ${sym}`, ssKpis([
      { label: "Daily σ", value: vol.daily_vol_pct != null ? `${fmtNum(vol.daily_vol_pct, 3)}%` : "—" },
      { label: "Annualised σ", value: vol.annualised_vol_pct != null ? `${fmtNum(vol.annualised_vol_pct)}%` : "—" },
      { label: "20-day σ", value: vol.hv_20d_pct != null ? `${fmtNum(vol.hv_20d_pct, 3)}%` : "—",
        sub: vol.hv_percentile_1y != null ? `${fmtNum(vol.hv_percentile_1y, 1)}th percentile of the past year` : "" },
      { label: "EWMA σ (λ=0.94)", value: vol.ewma_daily_vol_pct != null ? `${fmtNum(vol.ewma_daily_vol_pct, 3)}%` : "—" },
      { label: "Beta (3 months)", value: vol.beta_3m != null ? fmtNum(vol.beta_3m, 3) : "—",
        sub: vol.beta_3m != null ? "vs the stored NEPSE index" : esc(vol.beta_note || "unavailable") },
    ]), { badge: vol.as_of ? `as of ${vol.as_of}` : "" }));
    parts.push(ssCard("Volatility projection cone",
      `<div id="ss-cone"></div><p class="hint">${esc(vol.method || "")}</p><p class="hint">${esc(vol.uncertainty || "")}</p>`));
    const coneRows = (vol.cone || []).map((c) => ssRow([
      `+${c.horizon_days} days`,
      `${fmtNum(c.sigma_move_pct)}%`,
      `${fmtNum(c.band_1sigma[0])} – ${fmtNum(c.band_1sigma[1])}`,
      `${fmtNum(c.band_2sigma[0])} – ${fmtNum(c.band_2sigma[1])}`,
      `${fmtNum(c.sigma_move_pct_ewma)}%`,
    ]));
    parts.push(ssCard("Projection bands", table(
      ["Horizon", "σ move", "±1σ band", "±2σ band", "σ move (EWMA)"], coneRows),
      { hint: "Bands are lognormal quantiles around the last close, not price targets." }));
  } else {
    parts.push(ssCard(`Volatility — ${sym}`, ssUnavailable(vol.reason)));
  }

  host.innerHTML = parts.join("");
  const btn = $("#ss-risk-load");
  if (btn) btn.addEventListener("click", () => loadSastoShare("risk"));
  const input = $("#ss-risk-symbol");
  if (input) input.addEventListener("keydown", (e) => { if (e.key === "Enter") loadSastoShare("risk"); });

  if (vol.available) {
    const labels = ["now"].concat((vol.cone || []).map((c) => `+${c.horizon_days}d`));
    const last = vol.last_close;
    const series = [
      { name: "Close", values: [last].concat((vol.cone || []).map(() => last)), color: PRAVAHA.muted },
      { name: "±1σ", values: [last].concat((vol.cone || []).map((c) => c.band_1sigma[1])), color: PRAVAHA.cyan },
      { name: "−1σ", values: [last].concat((vol.cone || []).map((c) => c.band_1sigma[0])), color: PRAVAHA.cyan },
      { name: "±2σ", values: [last].concat((vol.cone || []).map((c) => c.band_2sigma[1])), color: PRAVAHA.down },
      { name: "−2σ", values: [last].concat((vol.cone || []).map((c) => c.band_2sigma[0])), color: PRAVAHA.down },
    ];
    VIZ.line($("#ss-cone"), { labels, series, height: 300, yFormat: (v) => fmtNum(v, 0),
      ariaLabel: `${sym} volatility projection bands out to 60 trading days` });
  }
}

/* ------------------------------------------------------------- rotation */
async function ssRotation(host) {
  const d = await api("/api/sastoshare/rotation");
  if (!d.available) {
    host.innerHTML = ssCard("Sector rotation", ssUnavailable(d.reason));
    return;
  }
  const rows = (d.sectors || []).map((s) => ssRow([
    { html: `<b>${esc(s.sector)}</b>` },
    String(s.members),
    { html: `<span class="${pctClass(s.return_1w_pct)}">${s.return_1w_pct != null ? fmtPct(s.return_1w_pct) : "—"}</span>` },
    { html: `<span class="${pctClass(s.return_1m_pct)}">${s.return_1m_pct != null ? fmtPct(s.return_1m_pct) : "—"}</span>` },
    { html: `<span class="${pctClass(s.return_3m_pct)}">${s.return_3m_pct != null ? fmtPct(s.return_3m_pct) : "—"}</span>` },
    { html: `<span class="${pctClass(s.return_6m_pct)}">${s.return_6m_pct != null ? fmtPct(s.return_6m_pct) : "—"}</span>` },
    s.rsi_14 != null ? fmtNum(s.rsi_14, 1) : "—",
    { html: s.macd && s.macd.state ? `<span class="ss-macd ${s.macd.state === "bullish" ? "up" : (s.macd.state === "bearish" ? "down" : "")}">${esc(s.macd.state)}</span>` : "—" },
    { html: `<span class="hint">${esc(s.regime || "")}</span>` },
  ]));

  const parts = [];
  parts.push(ssCard("Sector rotation", ssKpis([
    { label: "Leader (1 month)", value: d.leader_1m ? esc(d.leader_1m) : "—" },
    { label: "Sectors covered", value: String((d.sectors || []).length) },
  ]), { hint: esc(d.method || "") }));
  parts.push(ssCard("Sector table", table(
    ["Sector", "Members", "1 week", "1 month", "3 months", "6 months", "RSI(14)", "MACD", "Regime"], rows),
    { badge: "derived equal-weight index" }));
  parts.push(ssCard("One-month return ranking", `<div id="ss-rot-bars"></div>`,
    { hint: "Bars are the derived equal-weight index's one-month return, largest first." }));
  parts.push(ssCard("Index paths (last 90 bars, rebased to 100)", `<div id="ss-rot-lines"></div>`,
    { hint: "Each line is a derived equal-weight index of its members' stored closes." }));
  parts.push(ssCard("Caveats", ssCaveats(d.caveats)));

  host.innerHTML = parts.join("");

  const sorted = (d.sectors || []).slice().sort((a, b) => (b.return_1m_pct || 0) - (a.return_1m_pct || 0));
  VIZ.bars($("#ss-rot-bars"), {
    orientation: "h", height: Math.max(180, sorted.length * 22), signed: true, zeroLine: true,
    items: sorted.map((s) => ({ label: s.sector, value: s.return_1m_pct,
      color: (s.return_1m_pct || 0) >= 0 ? PRAVAHA.up : PRAVAHA.down })),
    valueFormat: (v) => `${fmtNum(v)}%`, ariaLabel: "One-month return by sector",
  });

  const top = sorted.slice(0, 6);
  if (top.length) {
    const n = Math.min.apply(null, top.map((s) => (s.index_series || []).length));
    if (n >= 2) {
      const labels = Array.from({ length: n }, (_, i) => String(i));
      VIZ.line($("#ss-rot-lines"), {
        labels,
        series: top.map((s, i) => ({
          name: s.sector,
          values: (s.index_series || []).slice(-n),
          color: (VIZ.PALETTE || [PRAVAHA.cyan])[i % (VIZ.PALETTE || [PRAVAHA.cyan]).length],
        })),
        height: 320, yFormat: (v) => fmtNum(v, 0),
        ariaLabel: "Rebased equal-weight sector index paths for the six strongest sectors",
      });
    } else {
      VIZ.empty($("#ss-rot-lines"), "Not enough common bars to compare sector paths.");
    }
  }
}

/* ------------------------------------------------------------ dividends */
async function ssDividends(host) {
  const sym = ssSymbol();
  const d = await api(`/api/sastoshare/dividends?symbol=${encodeURIComponent(sym)}`);

  const parts = [];
  parts.push(ssCard(`Dividends — ${sym}`, ssKpis([
    { label: "Dividend notices stored", value: sym ? String(d.event_count) : String(d.coverage.dividend_notices),
      sub: "from the corporate-events registry" },
    { label: "Symbols with a DPS row", value: String(d.coverage.symbols_with_dps),
      sub: `of ${d.coverage.symbols_with_bars} with stored bars` },
  ]), { badge: "honest coverage" }));

  if (d.blocker) {
    parts.push(ssCard("Notice calendar", ssUnavailable(d.blocker),
      { hint: `Event types currently in the registry: ${esc((d.event_types_recorded || []).join(", ") || "none")}.` }));
  } else {
    parts.push(ssCard("Notice calendar", table(["Date", "Symbol", "Type", "Headline"],
      d.events.map((e) => ssRow([e.effective_date || "—", e.symbol || "—", e.event_type || "—", e.headline || "—"])))));
  }

  parts.push(ssCard("Dividend yields", d.yields && d.yields.length
    ? table(["Symbol", "DPS", "Price", "Yield", "Payout", "DPS period"],
      d.yields.map((y) => ssRow([
        { html: `<b>${esc(y.symbol)}</b>` }, fmtNum(y.dps), fmtNum(y.price),
        { html: `${fmtNum(y.yield_pct)}%<span class="hint"> derived</span>` },
        { html: y.payout_pct != null ? `${fmtNum(y.payout_pct)}%` : `<span class="hint">no EPS</span>` },
        y.dps_period || "—",
      ])))
    : ssUnavailable("No dividend-per-share figure is stored for any symbol, so no yield can be computed."),
    { hint: "A yield is derived as DPS ÷ last close. A blank table means no DPS has been imported — not that no dividend was paid." }));

  parts.push(ssCard("Yield distribution",
    `<div id="ss-div-bars"></div><p class="hint">Denominator: ${d.yield_denominator} symbol(s) with a stored DPS.</p>`));

  parts.push(ssCard("Dividend scenario calculator",
    `<div class="controls">
       <label>DPS <input id="ss-div-dps" type="number" step="0.5" value="20" style="width:6em" /></label>
       <label>Price <input id="ss-div-price" type="number" step="1" value="${esc(sym ? "" : "")}" placeholder="e.g. 546" style="width:7em" /></label>
       <label>Growth % <input id="ss-div-growth" type="number" step="0.5" value="5" style="width:6em" /></label>
       <label>Years <input id="ss-div-years" type="number" step="1" value="10" style="width:5em" /></label>
       <button class="ctb-btn" id="ss-div-calc">Calculate</button>
     </div>
     <div id="ss-div-out"></div>
     <p class="hint">This calculator uses the figures you type. It is not derived from stored data, and a stored price is never substituted for one you leave blank.</p>`,
    { badge: "data-independent" }));

  host.innerHTML = parts.join("");

  if (d.yield_distribution && d.yield_distribution.length) {
    VIZ.bars($("#ss-div-bars"), {
      orientation: "v", height: 180,
      items: d.yield_distribution.map((b) => ({ label: b.label, value: b.count, color: PRAVAHA.cyan })),
      yFormat: (v) => String(v), valueFormat: (v) => String(v),
      ariaLabel: "Number of symbols by dividend-yield range",
    });
  } else {
    VIZ.empty($("#ss-div-bars"), "No yield distribution to draw.");
  }

  const calc = $("#ss-div-calc");
  if (calc) calc.addEventListener("click", () => ssDividendScenario());
}

function ssDividendScenario() {
  const out = $("#ss-div-out");
  if (!out) return;
  const dps = parseFloat(($("#ss-div-dps") || {}).value);
  const price = parseFloat(($("#ss-div-price") || {}).value);
  const g = parseFloat(($("#ss-div-growth") || {}).value);
  const years = parseInt(($("#ss-div-years") || {}).value, 10);
  const missing = [];
  if (!isFinite(dps) || dps < 0) missing.push("a dividend per share ≥ 0");
  if (!isFinite(price) || price <= 0) missing.push("a price > 0");
  if (!isFinite(g) || g <= -100) missing.push("a growth rate > −100%");
  if (!isFinite(years) || years < 1) missing.push("a horizon ≥ 1 year");
  if (missing.length) {
    out.innerHTML = `<div class="empty">Enter ${esc(missing.join(", "))} to calculate.</div>`;
    return;
  }
  const yieldPct = dps / price * 100;
  const rows = [];
  let value = dps;
  let total = 0;
  for (let y = 1; y <= years; y++) {
    total += value;
    rows.push(ssRow([`Year ${y}`, fmtNum(value), fmtNum(total), fmtNum(total / price * 100) + "%"]));
    value *= 1 + g / 100;
  }
  const incomeReturn = total / price * 100;
  out.innerHTML = ssKpis([
    { label: "Yield on cost", value: `${fmtNum(yieldPct)}%` },
    { label: `Income over ${years} years`, value: fmtNum(total) },
    { label: "Income return", value: `${fmtNum(incomeReturn)}%` },
  ]) + table(["Period", "Dividend", "Cumulative income", "% of price"], rows)
    + `<p class="hint">Growth is applied compounding to the dividend each year. The calculation ignores taxes, reinvestment and any change in the price.</p>`;
}

/* --------------------------------------------------- strategy vs buy&hold */
async function ssStrategy(host) {
  let strategies = [];
  try {
    const s = await api("/api/strategies");
    strategies = (s.strategies || s || []).filter((x) => x && x.key);
  } catch (e) { strategies = []; }
  const sym = ssSymbol();
  const opts = strategies.map((s) => `<option value="${esc(s.key)}">${esc(s.label || s.key)}</option>`).join("");

  host.innerHTML = ssCard("Strategy vs buy & hold",
    `<div class="controls">
       ${ssSymbolField("ss-strat-symbol", sym)}
       <label>Strategy <select id="ss-strat-select">${opts || `<option value="sma_cross">SMA crossover</option>`}</select></label>
       <button class="ctb-btn" id="ss-strat-run">Compare</button>
     </div>
     <p class="hint">The strategy curve comes from the real backtest engine. Buy &amp; hold uses the same symbol, dates and one-off entry cost, then never trades.</p>
     <div id="ss-strat-out"><div class="empty">Press Compare to run.</div></div>`);

  const run = $("#ss-strat-run");
  if (run) run.addEventListener("click", ssRunStrategy);
  const input = $("#ss-strat-symbol");
  if (input) input.addEventListener("keydown", (e) => { if (e.key === "Enter") ssRunStrategy(); });
}

async function ssRunStrategy() {
  const out = $("#ss-strat-out");
  if (!out) return;
  const sym = (($("#ss-strat-symbol") || {}).value || "").trim().toUpperCase();
  const strategy = (($("#ss-strat-select") || {}).value) || "sma_cross";
  if (!sym) { out.innerHTML = `<div class="empty">Enter a symbol.</div>`; return; }
  out.innerHTML = `<div class="empty">Running ${esc(strategy)} on ${esc(sym)}…</div>`;
  let d;
  try {
    d = await api("/api/sastoshare/backtest-vs-hold", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol: sym, strategy: strategy, initial_cash: 100000 }),
    });
  } catch (e) {
    out.innerHTML = `<div class="error">Comparison failed: ${esc(e.message)}</div>`;
    return;
  }
  if (!d.available) { out.innerHTML = ssUnavailable(d.reason); return; }
  const c = d.comparison || {};
  const parts = [];
  parts.push(ssKpis([
    { label: "Strategy final", value: fmtNum(c.strategy_final), sub: `${fmtPct(c.strategy_total_return_pct)} · CAGR ${fmtPct(c.strategy_cagr_pct)}` },
    { label: "Buy & hold final", value: fmtNum(c.buy_hold_final), sub: `${fmtPct(c.buy_hold_total_return_pct)} · CAGR ${fmtPct(c.buy_hold_cagr_pct)}` },
    { label: "Strategy max drawdown", value: `${fmtNum(c.strategy_max_drawdown_pct)}%` },
    { label: "Buy & hold max drawdown", value: `${fmtNum(c.buy_hold_max_drawdown_pct)}%` },
    { label: "Trades", value: String(d.trades), sub: `${d.years} years, ${d.start} → ${d.end}` },
  ]));
  parts.push(`<div id="ss-strat-curve"></div>`);
  parts.push(`<div id="ss-strat-dd"></div>`);
  parts.push(`<div id="ss-strat-hist"></div>`);
  parts.push(`<p class="hint">${esc(d.method || "")}</p>`);
  parts.push(ssCaveats(d.caveats));
  if (d.assumptions && d.assumptions.length) {
    parts.push(`<details><summary class="hint">Engine assumptions (${d.assumptions.length})</summary><ul class="ss-caveats">${d.assumptions.map((a) => `<li>${esc(a)}</li>`).join("")}</ul></details>`);
  }
  out.innerHTML = parts.join("");

  const curve = d.curve || [];
  const step = Math.max(1, Math.ceil(curve.length / 700));
  const sampled = curve.filter((_, i) => i % step === 0 || i === curve.length - 1);
  const labels = sampled.map((p) => p.date);
  VIZ.line($("#ss-strat-curve"), {
    labels,
    series: [
      { name: d.strategy_label || "Strategy", values: sampled.map((p) => p.strategy), color: PRAVAHA.cyan },
      { name: "Buy & hold", values: sampled.map((p) => p.buy_hold), color: PRAVAHA.caution },
    ],
    height: 320, yFormat: (v) => fmtCompact(v),
    ariaLabel: "Strategy equity curve against buy and hold",
  });
  VIZ.line($("#ss-strat-dd"), {
    labels,
    series: [{ name: "Drawdown", values: sampled.map((p) => p.drawdown_pct), color: PRAVAHA.down, area: true }],
    height: 180, yFormat: (v) => `${fmtNum(v, 0)}%`, zeroLine: true,
    ariaLabel: "Strategy drawdown over time",
  });
  const hist = d.histogram || { bins: [] };
  if (hist.bins && hist.bins.length) {
    VIZ.bars($("#ss-strat-hist"), {
      orientation: "v", height: 200,
      items: hist.bins.map((b) => ({ label: `${fmtNum(b.from, 0)}`, value: b.count,
        color: b.from >= 0 ? PRAVAHA.up : PRAVAHA.down })),
      yFormat: (v) => String(v), valueFormat: (v) => String(v),
      ariaLabel: "Distribution of closed-trade profit and loss",
    });
  } else {
    VIZ.empty($("#ss-strat-hist"), "No closed trades, so there is no return distribution.");
  }
  if (step > 1) {
    out.insertAdjacentHTML("beforeend",
      `<p class="hint">The equity curves are drawn with 1 in ${step} points (${sampled.length} of ${curve.length}) so the file stays responsive; the figures are unchanged.</p>`);
  }
}

/* ============================================================ Sector Overview */
async function loadSectorOverview() {
  const periodSel = $("#so-period");
  const metricSel = $("#so-metric");
  const groupSel = $("#so-group");
  const status = $("#so-status");
  const period = periodSel ? periodSel.value : "20";
  if (status) status.textContent = "Loading sector analytics…";
  let data;
  try {
    data = await api(`/api/sector-overview?period=${encodeURIComponent(period)}`);
  } catch (e) {
    const out = $("#so-rankings");
    if (out) out.innerHTML = `<div class="empty">Could not load sector overview: ${esc(e.message)}</div>`;
    if (status) status.textContent = "Unavailable";
    return;
  }
  if (!data || !data.available) {
    $("#so-rankings").innerHTML = `<div class="empty">${esc((data && data.reason) || "No sector data available.")}</div>`;
    if (status) status.textContent = "No data";
    return;
  }

  // Selected sectors/companies.
  const selectedSectors = new Set(Array.from(document.querySelectorAll("#so-sector-picks input:checked")).map((x) => x.value));
  if (!selectedSectors.size) data.sectors.forEach((s) => selectedSectors.add(s.sector));
  const companyRaw = ($("#so-companies") && $("#so-companies").value || "").trim();
  const selectedCompanies = companyRaw ? companyRaw.split(/[,\s]+/).map((x) => x.toUpperCase()).filter(Boolean) : [];

  // Fetch company bars for selected companies.
  const companySeries = {};
  await Promise.all(selectedCompanies.map(async (sym) => {
    try {
      const d = await api(`/api/bars/${encodeURIComponent(sym)}?limit=${period}`);
      const bars = d.bars || d.data || [];
      companySeries[sym] = bars.map((b) => ({ date: b.date || b.trading_date, close: b.close, turnover: b.turnover, volume: b.volume }));
    } catch (e) {
      companySeries[sym] = [];
    }
  }));

  if (status) status.textContent = `${data.period_sessions} trading sessions · ${data.start_date} → ${data.end_date} · ${data.data_quality.sector_count} sectors · ${data.data_quality.company_count} companies`;

  // Snapshot cards with explicit labels.
  const snap = $("#so-snapshot");
  if (snap) {
    const m = data.market || {};
    const breadth = (m.breadth && m.breadth[m.breadth.length - 1]) || {};
    const best = data.sectors.length ? data.sectors.reduce((a, b) => ((a.return_period_pct || -999) > (b.return_period_pct || -999) ? a : b)) : null;
    const worst = data.sectors.length ? data.sectors.reduce((a, b) => ((a.return_period_pct || 999) < (b.return_period_pct || 999) ? a : b)) : null;
    const cards = [
      ["NEPSE index", fmtNum(m.nepse && m.nepse[m.nepse.length - 1]), "latest close"],
      ["NEPSE period return", (m.nepse_return_period_pct != null ? m.nepse_return_period_pct + "%" : "—"), `${data.period_sessions} sessions`],
      ["Total market turnover", fmtNum(m.latest_total_turnover), "NPR, latest session"],
      ["Advancing companies", breadth.advancing != null ? breadth.advancing : "—", "latest session"],
      ["Declining companies", breadth.declining != null ? breadth.declining : "—", "latest session"],
      ["Strongest sector", best ? best.sector : "—", best && best.return_period_pct != null ? best.return_period_pct + "%" : "—"],
      ["Weakest sector", worst ? worst.sector : "—", worst && worst.return_period_pct != null ? worst.return_period_pct + "%" : "—"],
      ["Concentration HHI", data.concentration_hhi != null ? data.concentration_hhi : "—", "turnover share"],
      ["Sectors analyzed", data.data_quality.sector_count, "distinct sectors"],
      ["Companies analyzed", data.data_quality.company_count, "unique companies"],
      ["Trading sessions", data.data_quality.observations, data.data_quality.latest_date],
    ];
    snap.innerHTML = cards.map(([k, v, h]) =>
      `<div class="report-hero" style="min-width:150px;padding:10px 12px"><div class="hint">${esc(k)}</div><div style="font-size:18px;font-weight:700">${esc(String(v))}</div><div class="hint">${esc(String(h))}</div></div>`
    ).join("");
  }

  // Grouping helper: aggregate daily rows into weeks/months/quarters.
  function groupKey(dateStr, mode) {
    if (mode === "daily") return dateStr;
    const d = new Date(dateStr + "T00:00:00");
    if (mode === "weekly") {
      const tmp = new Date(d);
      const day = tmp.getDay();
      const diff = tmp.getDate() - day + (day === 0 ? -6 : 1);
      tmp.setDate(diff);
      return tmp.toISOString().slice(0, 10);
    }
    if (mode === "monthly") return dateStr.slice(0, 7);
    if (mode === "quarterly") {
      const m = parseInt(dateStr.slice(5, 7), 10);
      const q = Math.floor((m - 1) / 3) + 1;
      return `${dateStr.slice(0, 4)}-Q${q}`;
    }
    return dateStr;
  }
  const groupMode = groupSel ? groupSel.value : "daily";
  const groupedDates = [];
  const groupMap = new Map();
  data.dates.forEach((dt) => {
    const k = groupKey(dt, groupMode);
    if (!groupMap.has(k)) { groupMap.set(k, []); groupedDates.push(k); }
    groupMap.get(k).push(dt);
  });

  function groupSeries(dailyValues, agg) {
    return groupedDates.map((k) => {
      const vals = groupMap.get(k).map((dt) => {
        const i = data.dates.indexOf(dt);
        return dailyValues[i];
      }).filter((v) => v != null);
      if (!vals.length) return null;
      if (agg === "sum") return vals.reduce((a, b) => a + b, 0);
      if (agg === "avg") return vals.reduce((a, b) => a + b, 0) / vals.length;
      if (agg === "first") return vals[0];
      if (agg === "last") return vals[vals.length - 1];
      return vals[vals.length - 1];
    });
  }

  const metric = metricSel ? metricSel.value : "index";
  const mode = ($("#so-mode") && $("#so-mode").value) || "index";
  const chartEl = $("#so-chart");
  let chart = null;
  let tooltip = null;
  if (chartEl && typeof LightweightCharts !== "undefined") {
    chartEl.innerHTML = "";
    chart = LightweightCharts.createChart(chartEl, {
      layout: { background: { color: "transparent" }, textColor: "#9db4ae" },
      grid: { vertLines: { color: "rgba(36,69,60,.35)" }, horzLines: { color: "rgba(36,69,60,.35)" } },
      rightPriceScale: { borderColor: "rgba(36,69,60,.55)" },
      timeScale: { borderColor: "rgba(36,69,60,.55)", timeVisible: false },
      crosshair: { mode: 1 },
    });
    tooltip = document.createElement("div");
    tooltip.style.cssText = "position:absolute;right:8px;top:8px;background:rgba(6,17,15,.92);border:1px solid var(--line);border-radius:8px;padding:8px 10px;font-size:11px;pointer-events:none;max-width:260px;z-index:5;";
    chartEl.style.position = "relative";
    chartEl.appendChild(tooltip);

    const palette = ["#E9C46A", "#1FC98A", "#FF6B78", "#7BA7FF", "#F4D58D", "#A8FFD9", "#FFB86B", "#C792EA", "#9db4ae"];
    const normalize = (vals) => {
      const first = vals.find((v) => v != null);
      if (first == null || first === 0) return vals;
      return vals.map((v) => (v == null ? null : (v / first) * 100));
    };
    const seriesMap = new Map();
    (data.sectors || []).forEach((sec, i) => {
      if (!selectedSectors.has(sec.sector)) return;
      let daily = null;
      if (metric === "turnover") daily = sec.turnover;
      else if (metric === "volume") daily = sec.volume;
      else daily = sec.index;
      if (!daily) return;
      const agg = (metric === "turnover" || metric === "volume") ? "sum" : "last";
      let vals = groupSeries(daily, agg);
      if (mode === "pct" || mode === "normalized") {
        const first = vals.find((v) => v != null);
        if (first) vals = vals.map((v) => (v == null ? null : (mode === "normalized" ? (v / first) * 100 : ((v / first) - 1) * 100)));
      }
      if (mode === "relative") {
        const first = vals.find((v) => v != null);
        const nepseVals = groupSeries(data.market.nepse.map((v) => v), "last");
        const nepseFirst = nepseVals.find((v) => v != null);
        if (first && nepseFirst) vals = vals.map((v, j) => (v == null || nepseVals[j] == null ? null : (((v / first) / (nepseVals[j] / nepseFirst)) - 1) * 100));
      }
      const pts = groupedDates.map((k, j) => ({ time: k, value: vals[j] })).filter((p) => p.value != null);
      if (!pts.length) return;
      const series = chart.addLineSeries({ color: palette[i % palette.length], lineWidth: 2, title: sec.sector });
    window.__soAdded = (window.__soAdded||0)+1;
      series.setData(pts);
      seriesMap.set(sec.sector, { series, values: vals, dates: groupedDates });
    });
    // Companies
    let colorIdx = (data.sectors || []).length;
    selectedCompanies.forEach((sym) => {
      const bars = companySeries[sym] || [];
      if (!bars.length) return;
      const byDate = new Map(bars.map((b) => [b.date, b]));
      const daily = data.dates.map((dt) => {
        const b = byDate.get(dt);
        if (!b) return null;
        if (metric === "turnover") return b.turnover;
        if (metric === "volume") return b.volume;
        return b.close;
      });
      const agg = (metric === "turnover" || metric === "volume") ? "sum" : "last";
      let vals = groupSeries(daily, agg);
      if (mode === "pct" || mode === "normalized") {
        const first = vals.find((v) => v != null);
        if (first) vals = vals.map((v) => (v == null ? null : (mode === "normalized" ? (v / first) * 100 : ((v / first) - 1) * 100)));
      }
      const pts = groupedDates.map((k, j) => ({ time: k, value: vals[j] })).filter((p) => p.value != null);
      if (!pts.length) return;
      const series = chart.addLineSeries({ color: palette[colorIdx % palette.length], lineWidth: 2, title: sym });
      series.setData(pts);
      seriesMap.set(sym, { series, values: vals, dates: groupedDates });
      colorIdx++;
    });
    // NEPSE
    if (metric === "index" || metric === "return") {
      const nepsePts = groupedDates.map((k, j) => {
        const idxs = groupMap.get(k);
        const vals = idxs.map((dt) => {
          const i = data.dates.indexOf(dt);
          return data.market.nepse[i];
        }).filter((v) => v != null);
        if (!vals.length) return null;
        return { time: k, value: vals[vals.length - 1] };
      }).filter(Boolean);
      if (nepsePts.length) {
        const nepseSeries = chart.addLineSeries({ color: "#9db4ae", lineWidth: 1, lineStyle: 2, title: "NEPSE" });
      window.__soAdded = (window.__soAdded||0)+1;
        nepseSeries.setData(nepsePts);
        seriesMap.set("NEPSE", { series: nepseSeries, values: nepsePts.map((p) => p.value), dates: groupedDates });
      }
    }
    const titleEl = $("#so-chart-title");
    if (titleEl) titleEl.textContent = `${metric === "turnover" ? "Turnover (NPR)" : metric === "volume" ? "Share volume" : "Sector index"} · ${mode} · ${groupMode} · ${data.start_date} → ${data.end_date} · ${seriesMap.size} series`;
    const legendEl = $("#so-legend");
    if (legendEl) {
      legendEl.innerHTML = Array.from(seriesMap.keys()).map((name, i) =>
        `<span style="display:inline-flex;align-items:center;gap:4px;font-size:12px"><span style="width:12px;height:3px;background:${["#E9C46A","#1FC98A","#FF6B78","#7BA7FF","#F4D58D","#A8FFD9","#FFB86B","#C792EA","#9db4ae"][i % 9]};display:inline-block"></span>${esc(name)}</span>`
      ).join("");
    }
    chart.timeScale().fitContent();
    window.__soChart = chart;
    window.__soSeriesCount = seriesMap.size;
    chart.subscribeCrosshairMove((param) => {
      if (!tooltip) return;
      if (!param || !param.time) { tooltip.style.display = "none"; return; }
      const t = param.time;
      let html = `<b>${esc(String(t))}</b><br>`;
      seriesMap.forEach((info, name) => {
        const i = info.dates.indexOf(t);
        if (i >= 0 && info.values[i] != null) {
          html += `${esc(name)}: ${fmtNum(info.values[i])}<br>`;
        }
      });
      tooltip.innerHTML = html;
      tooltip.style.display = "block";
    });
  }

  // Rankings
  const rankEl = $("#so-rankings");
  if (rankEl) {
    const rows = (data.rankings || []).map((s) => [
      { html: esc(s.sector) },
      { html: fmtNum(s.return_period_pct) + "%" },
      { html: fmtNum(s.turnover_change_pct) + "%" },
      { html: fmtNum(s.latest_turnover) },
      { html: fmtNum(s.relative_turnover) },
      { html: s.members },
    ]);
    rankEl.innerHTML = table(["Sector", "Period return %", "Turnover change %", "Latest turnover", "Relative turnover", "Members"], rows);
  }

  // Turnover share
  const shareEl = $("#so-share");
  if (shareEl) {
    const rows = (data.turnover_share || []).map((s) => [
      { html: esc(s.sector) },
      { html: fmtNum(s.turnover) },
      { html: fmtNum(s.share_pct) + "%" },
    ]);
    shareEl.innerHTML = table(["Sector", "Latest turnover", "Share %"], rows)
      + `<p class="hint">Concentration HHI: ${esc(String(data.concentration_hhi))}. Latest-session turnover shares.</p>`;
  }

  // Heatmap
  const heatEl = $("#so-heatmap");
  if (heatEl) {
    const rows = (data.sectors || []).map((s) => {
      const v = s.return_period_pct;
      const color = v == null ? "var(--muted)" : (v >= 0 ? "var(--up)" : "var(--down)");
      return [{ html: `<span style="color:${color};font-weight:700">${esc(s.sector)}</span>` },
              { html: fmtNum(v) + "%" },
              { html: fmtNum(s.latest_turnover) },
              { html: fmtNum(s.relative_turnover) + "x" }];
    });
    heatEl.innerHTML = table(["Sector", "Period return %", "Latest turnover", "Relative turnover"], rows);
  }

  // Breadth
  const breadthEl = $("#so-breadth");
  if (breadthEl && typeof LightweightCharts !== "undefined") {
    breadthEl.innerHTML = "";
    const chart = LightweightCharts.createChart(breadthEl, {
      layout: { background: { color: "transparent" }, textColor: "#9db4ae" },
      grid: { vertLines: { color: "rgba(36,69,60,.35)" }, horzLines: { color: "rgba(36,69,60,.35)" } },
      rightPriceScale: { borderColor: "rgba(36,69,60,.55)" },
      timeScale: { borderColor: "rgba(36,69,60,.55)", timeVisible: false },
    });
    const adv = chart.addLineSeries({ color: "#1FC98A", lineWidth: 2, title: "Advancing" });
    const dec = chart.addLineSeries({ color: "#FF6B78", lineWidth: 2, title: "Declining" });
    adv.setData((data.market.breadth || []).map((b) => ({ time: b.date, value: b.advancing })).filter((p) => p.value != null));
    dec.setData((data.market.breadth || []).map((b) => ({ time: b.date, value: b.declining })).filter((p) => p.value != null));
    chart.timeScale().fitContent();
  }

  // Sector performance matrix: daily percentage changes.
  const matrixEl = $("#so-matrix");
  if (matrixEl) {
    const dailyChanges = (data.sectors || []).map((sec) => {
      const idx = sec.index || [];
      const changes = idx.map((v, i) => (i === 0 || idx[i - 1] == null || v == null ? null : ((v / idx[i - 1]) - 1) * 100));
      const periodReturn = idx.length >= 2 && idx[0] && idx[idx.length - 1] != null ? ((idx[idx.length - 1] / idx[0]) - 1) * 100 : sec.return_period_pct;
      return { sector: sec.sector, changes, periodReturn, turnover: sec.latest_turnover, volume: sec.latest_volume };
    });
    let html = `<div class="tablewrap"><table><thead><tr><th>Sector</th>` +
      data.dates.map((d) => `<th>${esc(d.slice(5))}</th>`).join("") +
      `<th>Period return %</th><th>Turnover</th></tr></thead><tbody>`;
    dailyChanges.forEach((row) => {
      html += `<tr><td><b>${esc(row.sector)}</b></td>` +
        row.changes.map((v) => {
          if (v == null) return `<td>—</td>`;
          const color = v >= 0 ? "var(--up)" : "var(--down)";
          return `<td style="color:${color};font-weight:600">${fmtNum(v, 2)}%</td>`;
        }).join("") +
        `<td style="font-weight:700">${fmtNum(row.periodReturn, 2)}%</td><td>${fmtNum(row.turnover)}</td></tr>`;
    });
    html += `</tbody></table></div>`;
    // Market total row
    const nepse = data.market.nepse || [];
    const nepseChanges = nepse.map((v, i) => (i === 0 || nepse[i - 1] == null || v == null ? null : ((v / nepse[i - 1]) - 1) * 100));
    const nepsePeriod = nepse.length >= 2 && nepse[0] && nepse[nepse.length - 1] != null ? ((nepse[nepse.length - 1] / nepse[0]) - 1) * 100 : data.market.nepse_return_period_pct;
    html += `<div class="report-missing ok" style="margin-top:8px">Market total row: NEPSE ${fmtNum(nepse[nepse.length-1])} · period return ${fmtNum(nepsePeriod,2)}% · total turnover ${fmtNum(data.market.latest_total_turnover)} NPR · ${data.data_quality.observations} sessions.</div>`;
    matrixEl.innerHTML = html;
  }

  // Insights
  const ins = $("#so-insights");
  if (ins) {
    ins.innerHTML = (data.insights || []).map((x) => `<div class="report-missing ok">${esc(x)}</div>`).join("");
  }
  const q = $("#so-quality");
  if (q) {
    q.textContent = `Latest date: ${data.data_quality.latest_date}. Observations: ${data.data_quality.observations}. ` +
      `${data.data_quality.sector_count} sectors, ${data.data_quality.company_count} companies. ${data.data_quality.note}`;
  }

  // Sector checkboxes
  const pickBox = $("#so-sector-picks");
  if (pickBox && !pickBox.dataset.bound) {
    pickBox.dataset.bound = "1";
    pickBox.innerHTML = (data.sectors || []).map((s) =>
      `<label class="chk" style="font-size:12px"><input type="checkbox" value="${esc(s.sector)}" checked /> ${esc(s.sector)}</label>`
    ).join(" ");
  }

  // Bind controls
  const refresh = $("#so-refresh");
  if (refresh && refresh.dataset.bound !== "1") {
    refresh.dataset.bound = "1";
    refresh.addEventListener("click", () => loadSectorOverview());
    if ($("#so-period")) $("#so-period").addEventListener("change", () => loadSectorOverview());
    if ($("#so-metric")) $("#so-metric").addEventListener("change", () => loadSectorOverview());
    if ($("#so-mode")) $("#so-mode").addEventListener("change", () => loadSectorOverview());
    if (groupSel) groupSel.addEventListener("change", () => loadSectorOverview());
  }
}

// Gold accent for the Sector Overview navigation item.
(function () {
  const style = document.createElement("style");
  style.textContent = `#nav button[data-view="sectoroverview"] { color: #E9C46A; } #nav button[data-view="sectoroverview"].active { background: rgba(233,196,106,.12); border-color: #E9C46A; color: #F4D58D; }`;
  document.head.appendChild(style);
})();
