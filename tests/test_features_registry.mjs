// Registry integrity tests for web/static/features.js.
//
// These are plain Node tests (no dependencies, no browser) so the registry can
// be validated against the REAL application: every `view` must exist in
// index.html and every scanner `preset` must be a real PRESET_SCREENS key in
// megatool/scanner.py. A registry entry that points at nothing is a bug.
//
//   node --test tests/test_features_registry.mjs

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");

function loadRegistry() {
  const src = readFileSync(join(ROOT, "web/static/features.js"), "utf8");
  const window = {};
  // The file is a plain IIFE that assigns window.PRAVAHA_FEATURES.
  new Function("window", src)(window);
  return window.PRAVAHA_FEATURES;
}

function realViews() {
  const html = readFileSync(join(ROOT, "web/static/index.html"), "utf8");
  const ids = new Set();
  for (const m of html.matchAll(/id="view-([A-Za-z0-9_-]+)"/g)) ids.add(m[1]);
  // Views that are rendered dynamically but still real destinations.
  for (const m of html.matchAll(/data-view="([A-Za-z0-9_-]+)"/g)) ids.add(m[1]);
  return ids;
}

function realPresets() {
  const py = readFileSync(join(ROOT, "megatool/scanner.py"), "utf8");
  const block = py.slice(py.indexOf("PRESET_SCREENS"));
  const keys = new Set();
  for (const m of block.matchAll(/^\s{4}"([a-z0-9_]+)"\s*:/gm)) keys.add(m[1]);
  return keys;
}

const F = loadRegistry();

test("registry loads and is non-trivial", () => {
  assert.ok(Array.isArray(F), "PRAVAHA_FEATURES must be an array");
  assert.ok(F.length >= 100, `expected a substantial registry, got ${F.length}`);
});

test("every entry has the required fields and a unique id", () => {
  const seen = new Set();
  for (const e of F) {
    assert.ok(e.id, `missing id: ${JSON.stringify(e).slice(0, 80)}`);
    assert.ok(!seen.has(e.id), `duplicate id: ${e.id}`);
    seen.add(e.id);
    assert.ok(e.name, `missing name for ${e.id}`);
    assert.ok(e.kind, `missing kind for ${e.id}`);
    assert.ok(e.category, `missing category for ${e.id}`);
  }
});

test("unavailable entries carry a reason and never claim a destination", () => {
  for (const e of F) {
    if (e.available === false) {
      assert.ok(e.reason && e.reason.length > 10, `${e.id} must state why it is unavailable`);
      assert.ok(!e.view, `${e.id} is unavailable and must not point at a view`);
    }
  }
});

test("every destination view actually exists in index.html", () => {
  const views = realViews();
  const missing = [];
  for (const e of F) {
    if (!e.view) continue;
    // `new` is the Company-Universe host view; its tabs are real sub-views.
    if (e.view === "new") continue;
    if (!views.has(e.view)) missing.push(`${e.id} -> view-${e.view}`);
  }
  assert.deepEqual(missing, [], "registry points at views that do not exist");
});

test("every scanner preset is a real PRESET_SCREENS key", () => {
  const presets = realPresets();
  assert.ok(presets.size > 20, `expected real presets, found ${presets.size}`);
  const bad = [];
  for (const e of F) {
    if (e.preset) {
      assert.equal(e.kind, "scanner", `${e.id} has a preset but is not a scanner`);
      if (!presets.has(e.preset)) bad.push(`${e.id} -> ${e.preset}`);
    }
  }
  assert.deepEqual(bad, [], "scanner presets that do not exist in scanner.py");
});

test("the user-facing command set resolves to a destination", () => {
  const need = [
    "dividend analysis", "eps history", "eps growth", "strategy vs buy",
    "seasonality", "holiday effect", "sector rotation", "top buyers",
    "top sellers", "buyer-seller pairs", "trade planner", "trade journal",
    "portfolio risk", "backtesting", "elliott wave", "fibonacci retracement",
    "fibonacci extension", "chart patterns", "money-flow oversold",
    "low volatility", "liquid by turnover", "graham", "lynch", "piotroski",
    "altman", "magic formula", "canslim", "multibagger", "book-value",
    "ttm eps", "market breadth", "relative strength", "data quality",
  ];
  const hay = F.map((e) => `${e.name} ${e.keywords || ""} ${e.id}`.toLowerCase());
  const missing = need.filter((n) => !hay.some((h) => h.includes(n)));
  assert.deepEqual(missing, [], "commands the user asked for that are not searchable");
});

test("chart-analysis layers are all searchable", () => {
  const layers = F.filter((e) => e.layer).map((e) => e.layer);
  for (const id of ["elliott", "fib", "patterns", "harmonic", "candles", "profile", "sr"]) {
    assert.ok(layers.includes(id), `analysis layer ${id} is not in the registry`);
  }
});

test("no entry advertises live data or fabricated capability", () => {
  const banned = /(live feed is connected|real[- ]time data|guaranteed profit)/i;
  for (const e of F) {
    const text = `${e.name} ${e.desc || ""} ${e.keywords || ""}`;
    assert.ok(!banned.test(text), `${e.id} overstates what it does`);
  }
});
