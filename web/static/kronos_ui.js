/* PRAVAHA — Kronos AI pages: AI Forecaster, Kronos AI, Algorithm Workshop,
   Tracing. Loaded after app.js so the shared helpers ($, $$, esc, api) and
   LightweightCharts are already available.

   Honesty rules:
   - forecast candles carry is_predicted=true from the server and are drawn in
     a clearly-labelled series, never merged into history;
   - evaluation metrics are shown NEXT TO the naive/drift baselines, and the
     verdict ("beats / does not beat the naive baseline") is computed, not
     asserted;
   - every failure renders as a state, not a fabricated result.
*/

/* global $, $$, esc, api, LightweightCharts */

window.MTKronos = (function () {
  "use strict";

  const state = {
    fcChart: null,
    fcVariantNote: "",
    status: null,
    catalogue: null,
  };

  /* ------------------------------------------------------------- helpers */
  const fmt = (v, d = 2) => (v === null || v === undefined || Number.isNaN(v) ? "—" : Number(v).toLocaleString("en", { maximumFractionDigits: d }));
  const pct = (v, d = 2) => (v === null || v === undefined ? "—" : `${fmt(v, d)}%`);

  async function guarded(button, work) {
    const original = button ? button.textContent : "";
    if (button) { button.disabled = true; button.textContent = "Working…"; }
    try {
      await work();
    } catch (e) {
      const msg = e.message || String(e);
      toast(msg);
      state.lastError = msg;
    } finally {
      if (button) { button.disabled = false; button.textContent = original; }
    }
  }

  let toastTimer = null;
  function toast(msg) {
    let el = $("#mt-toast");
    if (!el) {
      el = document.createElement("div");
      el.id = "mt-toast";
      document.body.appendChild(el);
    }
    el.className = "mt-toast";
    el.innerHTML = `<b>Note</b> ${esc(msg)}`;
    el.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { el.hidden = true; }, 7000);
  }

  /* ------------------------------------------------------- AI FORECASTER */
  function chartObservedVsPredicted(bars, preds, symbol, lastClose) {
    const host = $("#fc-chart");
    if (!host) return;
    host.innerHTML = "";
    if (state.fcChart) state.fcChart.remove?.();
    const chart = LightweightCharts.createChart(host, {
      height: 340,
      layout: { background: { color: "transparent" }, textColor: PRAVAHA.muted },
      grid: { vertLines: { color: "rgba(255,255,255,0.04)" }, horzLines: { color: "rgba(255,255,255,0.06)" } },
      rightPriceScale: { borderColor: "rgba(255,255,255,0.12)" },
      timeScale: { borderColor: "rgba(255,255,255,0.12)", timeVisible: false },
      crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
    });
    state.fcChart = chart;
    // observed: blue candle series
    const obs = chart.addCandlestickSeries({
      upColor: PRAVAHA.up, downColor: PRAVAHA.down, wickUpColor: PRAVAHA.up, wickDownColor: PRAVAHA.down,
      borderUpColor: PRAVAHA.cyan, borderDownColor: PRAVAHA.cyan, priceLineVisible: true,
    });
    obs.setData(bars.map((b) => ({
      time: b.time, open: b.open, high: b.high, low: b.low, close: b.close,
    })));
    // predicted: amber candles (nothing is drawn before the first prediction)
    const prd = chart.addCandlestickSeries({
      upColor: PRAVAHA.caution, downColor: PRAVAHA.caution, wickUpColor: PRAVAHA.caution, wickDownColor: PRAVAHA.caution,
      borderUpColor: PRAVAHA.caution, borderDownColor: PRAVAHA.caution, priceLineVisible: false,
      lastValueVisible: false,
    });
    prd.setData(preds.map((r) => ({ time: r.time, open: r.open, high: r.high, low: r.low, close: r.close })));
    if (preds.length) prd.createPriceLine?.({
      price: lastClose, color: "rgba(247,181,0,0.35)", lineWidth: 1, axisLabelVisible: false,
    });
    chart.timeScale().fitContent();
  }

  async function fcRun() {
    const btn = $("#fc-load");
    await guarded(btn, async () => {
      const symbol = ($("#fc-symbol").value || "").trim().toUpperCase();
      if (!symbol) { toast("Type a symbol to forecast (e.g. NIMB)."); return; }
      const payload = {
        symbol,
        pred_len: Number($("#fc-pred").value || 10),
        context_len: Number($("#fc-context").value || 256),
        variant: $("#fc-variant").value,
        device: $("#fc-device").value || null,
      };
      progress(true, "Loading official weights (first run takes a few seconds), then forecasting …");
      try {
        const result = await api("/api/kronos/forecast", { method: "POST", body: JSON.stringify(payload), headers: { "Content-Type": "application/json" } });
        renderForecast(result);
        fillSavedList();
      } finally {
        progress(false);
      }
      state.lastError = null;
    });
  }

  function progress(on, note) {
    const box = $("#fc-progress");
    if (!box) return;
    box.hidden = !on;
    if (note) $("#fc-progress-note").textContent = note;
    if (on) {
      const bar = $("#fc-progress-bar").firstElementChild;
      bar.style.animation = "mt-slide 1.6s ease-in-out infinite";
    }
  }

  let lastEvalResult = null;
  async function fcEvaluate() {
    const btn = $("#fc-evaluate");
    await guarded(btn, async () => {
      const symbol = ($("#fc-symbol").value || "").trim().toUpperCase();
      if (!symbol) { toast("Type a symbol to evaluate (e.g. NIMB)."); return; }
      const payload = {
        symbol,
        pred_len: Number($("#fc-pred").value || 5),
        context_len: Number($("#fc-context").value || 256),
        variant: $("#fc-variant").value,
        windows: 6,
        device: $("#fc-device").value || null,
      };
      progress(true, "Walking forward through history — this runs several real model fits …");
      try {
        const result = await api("/api/kronos/evaluate", { method: "POST", body: JSON.stringify(payload), headers: { "Content-Type": "application/json" } });
        lastEvalResult = result;
        renderEvaluate(result);
      } finally {
        progress(false);
      }
    });
  }

  function chip(label, value, cls = "") {
    return `<div class="chip ${cls}"><span class="chip-label">${esc(label)}</span><b>${value}</b></div>`;
  }

  function renderForecast(result) {
    $("#fc-report").hidden = false;
    $("#fc-head-symbol").textContent = `${result.symbol} · Kronos-${result.variant}`;
    const ctx = result.context;
    $("#fc-meta").innerHTML =
      chip("context bars", fmt(ctx.bars, 0)) +
      chip("history span", `${ctx.first} → ${ctx.last}`) +
      chip("last close", fmt(ctx.last_close)) +
      chip("device", esc(result.device)) +
      chip("inference", `${fmt(result.inference_seconds, 2)} s`) +
      chip("load", `${fmt(result.load_seconds, 2)} s`);
    $("#fc-notes").textContent = result.note || "";
    const rows = result.rows.map((r) => [
      r.time,
      { html: fmt(r.open), cls: "" },
      { html: fmt(r.high), cls: "" },
      { html: fmt(r.low), cls: "" },
      { html: `<b>${fmt(r.close)}</b>`, cls: r.close >= result.context.last_close ? "up" : "down" },
      { html: `<span class="pill pill-warn">predicted</span>`, cls: "" },
    ]);
    $("#fc-table").innerHTML = table(["date", "open", "high", "low", "close", "label"], rows);

    // §5.21/K: hand this exact forecast to the main chart. The SAME rows are
    // drawn there — no second model run — and the payload is stamped so the
    // chart can show when it was generated and never treat it as observed.
    const shareRow = $("#fc-share-row");
    if (shareRow) {
      const payload = {
        symbol: result.symbol, variant: result.variant, rows: result.rows,
        context: result.context, device: result.device,
        inference_seconds: result.inference_seconds, load_seconds: result.load_seconds,
        note: result.note || "", generated_at: new Date().toISOString(),
      };
      try { localStorage.setItem("mt-kronos-share", JSON.stringify(payload)); } catch (e) { /* storage full */ }
      const btn = document.createElement("button");
      btn.className = "ghost";
      btn.id = "fc-view-on-chart";
      btn.title = "Copy this forecast onto the main charting view — the same rows, marked PREDICTED";
      btn.textContent = "View last forecast on chart";
      btn.addEventListener("click", () => {
        if (typeof window.mtAppShareForecast === "function") {
          window.mtAppShareForecast(payload);
        } else {
          toast("Charting module is still loading — try again in a moment.");
        }
      });
      shareRow.innerHTML = "";
      shareRow.appendChild(btn);
    }

    // chart: observed + predicted
    const ctxBars = 90;
    fetch(`/api/bars/${encodeURIComponent(result.symbol)}?limit=${ctxBars + 1}`).then((r) => r.json()).then((d) => {
      chartObservedVsPredicted(d.bars || [], result.rows, result.symbol, result.context.last_close);
    });
  }

  function renderEvaluate(result) {
    const a = result.avg;
    const beats = (a.kronos_mae_close ?? Infinity) < (a.naive_mae_close ?? Infinity);
    $("#fc-eval").hidden = false;
    $("#fc-eval-summary").innerHTML =
      chip("windows", fmt(a.windows, 0)) +
      chip("horizon", `${a.horizon} d`) +
      chip("Kronos MAE", fmt(a.kronos_mae_close), "warn") +
      chip("naive MAE", fmt(a.naive_mae_close)) +
      chip("drift20 MAE", fmt(a.drift20_mae_close)) +
      chip("direction agree", pct(a.kronos_direction_pct), a.kronos_direction_pct >= 50 ? "up" : "warn") +
      chip("runtime", `${fmt(a.total_seconds, 1)} s`);
    const rows = result.windows_detail.map((w) => [
      w.anchor,
      w.realized_span,
      fmt(w.kronos.mae),
      fmt(w.kronos.mape_pct),
      `${w.kronos.direction_ok}/${w.kronos.steps}`,
      fmt(w.naive_last_close.mae),
      fmt(w.drift20.mae),
    ]);
    $("#fc-eval-table").innerHTML = table(
      ["anchor", "realized range", "Kronos MAE", "Kronos MAPE %", "dir OK", "naive MAE", "drift20 MAE"], rows);
    $("#fc-eval-note").textContent =
      `Verdict on this measurement: the Kronos forecast ${beats ? "beats" : "does NOT beat"} the naive last-close baseline. ` +
      (beats ? "" : "A sampled foundation-model path is not automatically better than repeating the last close — treat the numbers above as the evidence.") +
      " " + result.note;
  }

  function exportEvalCsv() {
    if (!lastEvalResult || !Array.isArray(lastEvalResult.windows_detail)) { toast("Run 'Evaluate vs baselines' first."); return; }
    const rows = lastEvalResult.windows_detail;
    const header = ["anchor", "realized_span", "kronos_mae", "kronos_mape_pct", "kronos_dir_ok", "kronos_steps", "naive_mae", "drift20_mae"];
    const lines = [header.join(",")];
    for (const w of rows) {
      lines.push([
        w.anchor, w.realized_span,
        w.kronos?.mae, w.kronos?.mape_pct, w.kronos?.direction_ok, w.kronos?.steps,
        w.naive_last_close?.mae, w.drift20?.mae,
      ].map((v) => (v == null ? "" : String(v))).join(","));
    }
    const blob = new Blob([lines.join("\\n")], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `kronos-eval-${lastEvalResult.symbol || "symbol"}-${new Date().toISOString().slice(0,10)}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  function fillSavedList() {
    api("/api/kronos/experiments").then((d) => {
      const host = $("#fc-saved");
      if (!d.experiments.length) { host.innerHTML = `<div class="empty">No saved forecast yet.</div>`; renderKronosExperiments(d.experiments); return; }
      const rows = d.experiments.map((e) => [
        `<span class="hint">${esc(e.created_at || "")}</span>`,
        e.kind,
        `<b>${esc(e.symbol)}</b>`,
        esc(e.variant),
        e.kind === "forecast" ? `${e.pred_len}d @ ctx${e.context_len}` : `${e.pred_len}d × ${e.kind === "evaluate" ? (e.params?.windows ?? "?") : "?"} win`,
        { html: `<span class="hint">${fmt(e.inference_seconds, 2)} s</span>`, cls: "" },
        { html: `<button class="ghost" data-kron-del="${e.id}">delete</button>`, cls: "" },
      ]);
      host.innerHTML = table(["saved at", "kind", "symbol", "model", "config", "runtime", ""], rows);
      renderKronosExperiments(d.experiments);
      $$("#fc-saved [data-kron-del]").forEach((b) =>
        b.addEventListener("click", () => {
          api(`/api/kronos/experiments/${b.dataset.kronDel}`, { method: "DELETE" }).then(fillSavedList);
        })
      );
    }).catch(() => {});
  }

  /* --------------------------------------------------------- KRONOS AI  */
  async function loadKronosStatus() {
    try {
      const s = await api("/api/kronos/status");
      state.status = s;
      const w = s.weights || {};
      const ready = ["Kronos-Base", "Kronos-small", "Kronos-mini", "Kronos-Tokenizer-base"]
        .filter((k) => w[k] && w[k].present);
      $("#kron-availability").innerHTML =
        chip("torch", s.torch_installed ? "installed" : "MISSING", s.torch_installed ? "up" : "down") +
        chip("einops", s.einops_installed ? "installed" : "MISSING", s.einops_installed ? "up" : "down") +
        chip("device", esc(s.device_selected), s.device_selected === "unavailable" ? "down" : "up") +
        chip("files on disk", `${ready.length}/4`) +
        chip("official id", "NeoQuasar/*");
      $("#kron-weights").innerHTML = table(
        ["official repository", "file", "present", "bytes"],
        Object.entries(w).map(([k, v]) => [
          `NeoQuasar/${k}`,
          "model.safetensors + config.json",
          v.present ? `<span class="pill ok">present</span>` : `<span class="pill down">absent</span>`,
          v.bytes ? fmt(v.bytes / 1e6, 1) + " MB" : "—",
        ]));
      loadKronosRuntime();
    } catch (e) {
      $("#kron-availability").innerHTML = `<span class="down">Status unavailable: ${esc(e.message)}</span>`;
    }
  }

  function loadKronosRuntime() {
    const s = state.status || {};
    const vmx = s.variant_max_context || {};
    $("#kron-runtime").innerHTML =
      chip("resident variant", esc(s.loaded_variant || "not loaded"), s.loaded_variant ? "up" : "warn") +
      chip("load time", s.load_seconds ? `${fmt(s.load_seconds, 2)} s` : "—") +
      chip("device", esc(s.device_selected || "—")) +
      chip("context limits", Object.keys(vmx).length
        ? Object.entries(vmx).map(([v, n]) => `${v} ${n}`).join(" · ")
        : fmt(s.max_context || 512, 0));
    $("#kron-runtime-note").textContent =
      "The model loads lazily on the first forecast and stays resident until unloaded. " +
      "Only one variant is resident at a time. Mini is paired with the official Kronos-Tokenizer-2k.";

    $("#kron-facts").innerHTML = table(
      ["property", "value"],
      [
        ["paper", "Kronos: A Foundation Model for the Language of Financial Markets"],
        ["licence", "MIT (code + weights)"],
        ["architecture", "tokenizer (BSQ) + autoregressive transformer, d_model 832, 12 layers (Base)"],
        ["official repos", "github.com/shiyu-coder/Kronos · huggingface.co/NeoQuasar"],
        ["context limit", `512 bars (Base & Small) · 2048 bars (Mini, Tokenizer-2k)`],
        ["verified here", "official regression suite passed with local weights (rel err < 1e-6)"],
        ["what it predicts", "future OHLC + volume + amount candle paths (samples, labelled)"],
        ["what it never does", "live NEPSE quotes, orders, broker access, guaranteed profit"],
      ]);
  }

  async function renderKronosExperiments(items) {
    const host = $("#kron-experiments");
    if (!host) return;
    if (!items) {
      const d = await api("/api/kronos/experiments").catch(() => null);
      items = d ? d.experiments : [];
    }
    if (!items.length) { host.innerHTML = `<div class="empty">No runs recorded yet — run one from the AI Forecaster.</div>`; return; }
    const rows = items.slice(0, 40).map((e) => [
      esc(e.created_at || ""),
      e.kind,
      `<b>${esc(e.symbol)}</b>`,
      esc(e.variant),
      esc(e.device || "—"),
      { html: `<span class="hint">${fmt(e.inference_seconds, 2)} s</span>`, cls: "" },
      { html: `<button class="ghost" data-kron-del="${e.id}">delete</button>`, cls: "" },
    ]);
    host.innerHTML = table(["when", "kind", "symbol", "model", "device", "runtime", ""], rows);
    $$("#kron-experiments [data-kron-del]").forEach((b) =>
      b.addEventListener("click", async () => {
        await api(`/api/kronos/experiments/${b.dataset.kronDel}`, { method: "DELETE" });
        renderKronosExperiments();
      })
    );
  }

  /* ------------------------------------------------- ALGORITHM WORKSHOP */
  async function loadWorkshop() {
    const host = $("#ws-catalogue");
    try {
      const d = await api("/api/strategies");
      state.catalogue = d.strategies;
      $("#ws-count").textContent = `${d.strategies.length} candidates registered`;
      $("#ws-banner").textContent =
        "Research evaluation of strategies over stored history. Not advice; no orders.";
      const allOn = new URLSearchParams(location.search).get("wsall") === "1";
      host.innerHTML = table(
        ["", "key", "algorithm", "category", "what it does", "parameters"],
        d.strategies.map((s) => [
          `<input type="checkbox" class="ws-strategy" value="${esc(s.key)}" checked />`,
          { html: `<code>${esc(s.key)}</code>`, cls: "" },
          `<b>${esc(s.label)}</b>`,
          esc(s.category || "—"),
          esc(s.description || ""),
          esc(Object.entries(s.params || {}).map(([k, v]) => `${k}=${v}`).join(", ") || "—"),
        ]));
    } catch (e) {
      host.innerHTML = `<div class="down">Catalogue unavailable: ${esc(e.message)}</div>`;
    }
  }

  async function runWorkshop() {
    const btn = $("#ws-run");
    await guarded(btn, async () => {
      const symbol = ($("#ws-symbol").value || "").trim().toUpperCase();
      if (!symbol) { toast("Type a symbol (e.g. NABIL)."); return; }
      const keys = $$(".ws-strategy:checked").map((c) => c.value);
      if (!keys.length) { toast("Select at least one algorithm."); return; }
      const range = Number($("#ws-range").value || 0);
      const start = range ? new Date(Date.now() - range * 86400000).toISOString().slice(0, 10) : undefined;
      const results = [];
      progress(true, `Backtesting ${keys.length} algorithm(s) on ${symbol} …`);
      try {
        for (const key of keys) {
          const body = { symbol, strategy: key };
          if (start) body.start = start;
          const d = await api("/api/backtest", {
            method: "POST",
            body: JSON.stringify(body),
            headers: { "Content-Type": "application/json" },
          });
          results.push({ key, ...d });
        }
        renderWorkshopResults(results, symbol);
      } finally {
        progress(false);
      }
    });
  }

  function renderWorkshopResults(results, symbol) {
    $("#ws-results-card").hidden = false;
    $("#ws-results-meta").textContent = `${results.length} algorithm(s) · ${symbol} · next-open execution · whole units`;
    results.sort((x, y) => Number(y?.metrics?.total_return_pct ?? -1e9) - Number(x?.metrics?.total_return_pct ?? -1e9));
    const rows = results.map((r) => {
      const m = r.metrics || {};
      return [
        `<b>${esc(m.strategy_label || r.key)}</b>`,
        pct(m.total_return_pct),
        pct(m.cagr_pct),
        fmt(m.sharpe),
        pct(m.max_drawdown_pct),
        fmt(m.win_rate_pct, 1),
        fmt(m.trades, 0),
      ];
    });
    $("#ws-results").innerHTML = table(
      ["algorithm", "total return", "CAGR", "Sharpe", "max DD", "win rate", "trades"], rows) +
      `<p class="hint">Total return, CAGR, Sharpe and drawdown are computed from the stored bars with the engine's stated assumptions. A ranking at the top is a historical measurement on one symbol — not evidence of future results.</p>`;
  }

  function readable_rule(a) {
    // The stored key is a hash; the human-readable rule lives in the message
    // ("NABIL closed at 546, below the 600 threshold"). Show the *statement*,
    // keep the hash available in the message column.
    const msg = a.message || "";
    if (a.symbol && msg.startsWith(a.symbol)) {
      return msg.slice(a.symbol.length).trim().replace(/^\W+/, "").slice(0, 60);
    }
    return `${a.symbol || ""} ${a.condition || a.alert_key || ""}`.trim();
  }

  /* ----------------------------------------------------------- TRACING  */
  async function loadTracing() {
    api("/api/alerts/history?limit=200").then((d) => {
      const host = $("#trace-alerts");
      const items = d.alerts || [];
      if (!items.length) { host.innerHTML = `<div class="empty">No alerts recorded. Configure and Evaluate on the Dashboard.</div>`; return; }
      const rows = items.map((a) => [
        esc(a.created_at || ""),
        esc(readable_rule(a)),
        `<b>${esc(a.symbol || "")}</b>`,
        esc(a.message || ""),
        esc(a.severity || ""),
        fmt(a.fire_count, 0),
        a.acknowledged_at ? esc(a.acknowledged_at) : `<span class="hint">open</span>`,
      ]);
      host.innerHTML = table(["when", "rule", "symbol", "message", "severity", "fires", "acked"], rows);
    }).catch((e) => {
      $("#trace-alerts").innerHTML = `<div class="down">History unavailable: ${esc(e.message)}</div>`;
    });
    api("/api/journal?limit=60").then((d) => {
      const host = $("#trace-journal");
      const items = d.entries || d || [];
      if (!items.length) { host.innerHTML = `<div class="empty">No journal entries yet.</div>`; return; }
      const rows = items.map((j) => [
        esc(j.created_at || ""),
        `<b>${esc(j.symbol || "")}</b>`,
        esc(j.action || j.side || ""),
        esc(String(j.reason || j.note || "")),
      ]);
      host.innerHTML = table(["when", "symbol", "action", "reason"], rows);
    }).catch(() => {
      $("#trace-journal").innerHTML = `<div class="empty">Journal history unavailable.</div>`;
    });
  }

  function table(headers, rows) {
    if (!rows || !rows.length) return `<div class="empty">Nothing to show.</div>`;
    const head = headers.map((h) => `<th>${esc(h)}</th>`).join("");
    const body = rows.map((r) => `<tr>${r.map((c) => `<td class="${typeof c === "object" && c !== null ? c.cls || "" : ""}">${typeof c === "object" && c !== null ? c.html : c}</td>`).join("")}</tr>`).join("");
    return `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
  }

  /* ------------------------------------------------------------- router */
  function onShow(view) {
    if (view === "forecaster") {
      fillSavedList();
      if (!$("#fc-symbol").value) {
        const fromChart = ($("#symbol-input").value || "").trim();
        if (fromChart) $("#fc-symbol").value = fromChart.toUpperCase();
      }
      updateVariantNote();
    } else if (view === "kronos") {
      loadKronosStatus();
      renderKronosExperiments();
    } else if (view === "workshop") {
      loadWorkshop();
    } else if (view === "tracing") {
      loadTracing();
    }
  }

  async function updateVariantNote() {
    try {
      if (!state.status) state.status = await api("/api/kronos/status");
      const w = state.status.weights || {};
      const variant = $("#fc-variant").value;
      const folder = { base: "Kronos-base", small: "Kronos-small", mini: "Kronos-mini" }[variant] || variant;
      const v = w[folder];
      const cx = (state.status.variant_max_context || {})[variant];
      const tok = (state.status.variant_tokenizer || {})[variant];
      $("#fc-variant-note").textContent = v && v.present
        ? `official weights on disk (${fmt(v.bytes / 1e6, 0)} MB)` +
          (cx ? ` · context ≤ ${fmt(cx, 0)} bars` : "") +
          (tok && /2k/.test(tok) ? " · official Tokenizer-2k" : "")
        : "weights missing — will refuse, not fake";
    } catch (_) { /* status may fail before backend has torch info */ }
  }

  function wire() {
    if (document.getElementById("fc-load")) {
      $("#fc-load").addEventListener("click", fcRun);
      $("#fc-evaluate").addEventListener("click", fcEvaluate);
  const exportBtn = $("#fc-eval-export");
  if (exportBtn) exportBtn.addEventListener("click", exportEvalCsv);
      $("#fc-list-refresh").addEventListener("click", fillSavedList);
      $("#fc-symbol").addEventListener("keydown", (e) => { if (e.key === "Enter") fcRun(); });
      $("#fc-variant").addEventListener("change", updateVariantNote);
      $("#fc-status").addEventListener("click", () => guarded($("#fc-status"), async () => {
        state.status = await api("/api/kronos/status");
        await updateVariantNote();
        toast("Model status refreshed.");
      }));
    }
    if (document.getElementById("kron-refresh")) {
      $("#kron-refresh").addEventListener("click", () => guarded($("#kron-refresh"), async () => {
        state.status = null;
        await loadKronosStatus();
        toast("Kronos status refreshed.");
      }));
      $("#kron-unload").addEventListener("click", () => guarded($("#kron-unload"), async () => {
        await api("/api/kronos/unload", { method: "POST" });
        state.status = null;
        await loadKronosStatus();
        toast("Resident model unloaded; it reloads on the next forecast.");
      }));
      $("#kron-exp-refresh").addEventListener("click", () => renderKronosExperiments());
    }
    if (document.getElementById("ws-run")) {
      $("#ws-run").addEventListener("click", runWorkshop);
      $("#ws-symbol").addEventListener("keydown", (e) => { if (e.key === "Enter") runWorkshop(); });
      $("#ws-check-all").addEventListener("click", () => $$(".ws-strategy").forEach((c) => { c.checked = true; }));
      $("#ws-check-none").addEventListener("click", () => $$(".ws-strategy").forEach((c) => { c.checked = false; }));
    }
    if (document.getElementById("trace-refresh")) {
      $("#trace-refresh").addEventListener("click", loadTracing);
      $("#trace-journal-refresh").addEventListener("click", loadTracing);
      $("#trace-clear").addEventListener("click", () =>
        guarded($("#trace-clear"), async () => {
          await api("/api/alerts/clear", { method: "DELETE" });
          toast("Alert history cleared — all conditions re-armed.");
          loadTracing();
        })
      );
    }
  }

  document.addEventListener("DOMContentLoaded", wire);

  return { onShow, loadTracing, loadWorkshop, toast };
})();
