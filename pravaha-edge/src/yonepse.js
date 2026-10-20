// Pure, testable logic for the PRAVAHA scheduled YONEPSE refresh.
//
// Source: https://shubhamnpk.github.io/yonepse  (docs: pages/docs.html)
//   * No authentication. Public JSON only.
//   * The docs state the datasets update "every hour (Mon-Fri, 11 AM-4 PM NPT)".
//     A 30-minute cron therefore usually re-reads an UNCHANGED dataset — which
//     is why this module records "unchanged" instead of treating it as a
//     failure, and why the caller skips the write when nothing changed.
//
// Nothing here fabricates data. The per-symbol quote board is an LTP snapshot:
// it is summarised (counts + newest timestamp) and NEVER turned into historical
// OHLCV candles.

//: The documented base (GitHub Pages mirror).
export const YONEPSE_BASE = "https://shubhamnpk.github.io/yonepse";

//: The repository's raw content. MEASURED 2026-10-19: the Pages mirror is
//: CDN-cached and served `status.json` three days stale (`last_checked`
//: 2026-10-16T10:17 vs 2026-10-19T10:17 on raw), which made a healthy,
//: market-closed source look "stale". Raw is read FIRST and Pages is the
//: fallback — the same ordering `megatool/datasources/yonepse.py` already uses.
export const YONEPSE_RAW_BASE =
  "https://raw.githubusercontent.com/Shubhamnpk/yonepse/main";

export const YONEPSE_BASES = [YONEPSE_RAW_BASE, YONEPSE_BASE];

//: Datasets fetched by the scheduled job. Small, documented, public.
//: `shape` is the validation contract (see validateDataset).
export const DATASETS = [
  { key: "status", path: "data/market/status.json", shape: "object" },
  { key: "indices", path: "data/market/indices.json", shape: "array" },
  { key: "summary", path: "data/market/summary.json", shape: "array" },
  { key: "sectorIndices", path: "data/market/sector_indices.json", shape: "array" },
  { key: "history", path: "data/market/history.json", shape: "array-or-object" },
  { key: "ltpManifest", path: "data/ltp/manifest.json", shape: "object" },
  { key: "quotes", path: "data/nepse_data.json", shape: "array" },
];

// --------------------------------------------------------------------- market clock
// Nepal is UTC+05:45 with no DST. Compute NPT wall-clock parts from a UTC instant.
export function nptParts(date = new Date()) {
  const ms = date.getTime() + (5 * 60 + 45) * 60 * 1000;
  const d = new Date(ms);
  return {
    year: d.getUTCFullYear(),
    month: d.getUTCMonth() + 1,
    day: d.getUTCDate(),
    hour: d.getUTCHours(),
    minute: d.getUTCMinutes(),
    weekday: d.getUTCDay(), // 0 = Sunday
    iso: `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}-${String(
      d.getUTCDate()
    ).padStart(2, "0")}T${String(d.getUTCHours()).padStart(2, "0")}:${String(
      d.getUTCMinutes()
    ).padStart(2, "0")}:${String(d.getUTCSeconds()).padStart(2, "0")}+05:45`,
  };
}

//: NEPSE trading session, NPT. The docs give 11:00–15:00 as market hours and
//: 11:00–16:00 as the scraper's publishing window; we treat the WIDER window as
//: "worth polling" so we never miss a late publish.
export const MARKET_OPEN_HOUR = 11;
export const MARKET_CLOSE_HOUR = 16;

export function isTradingDay(date = new Date()) {
  const w = nptParts(date).weekday;
  return w >= 1 && w <= 5; // Mon–Fri
}

export function isMarketWindow(date = new Date()) {
  const p = nptParts(date);
  return isTradingDay(date) && p.hour >= MARKET_OPEN_HOUR && p.hour < MARKET_CLOSE_HOUR;
}

// --------------------------------------------------------------------- validation
export function shapeOf(data) {
  if (Array.isArray(data)) return "array";
  if (data && typeof data === "object") return "object";
  return typeof data;
}

/**
 * Validate a parsed payload against its declared shape. Returns null when OK,
 * or a short reason string. A malformed payload must never be stored.
 */
export function validateDataset(path, data, shape) {
  const got = shapeOf(data);
  const ok =
    shape === "array-or-object" ? got === "array" || got === "object" : got === shape;
  if (!ok) return `${path}: expected ${shape}, got ${got}`;
  if (shape === "array" && data.length === 0) return `${path}: empty array`;
  if (shape === "object" && Object.keys(data).length === 0) return `${path}: empty object`;
  if (path.endsWith("status.json")) {
    if (typeof data.is_open !== "boolean") return `${path}: is_open is not a boolean`;
    if (typeof data.last_checked !== "string") return `${path}: last_checked missing`;
  }
  if (path.endsWith("nepse_data.json") || path.endsWith("indices.json")) {
    const first = data[0];
    if (!first || typeof first !== "object") return `${path}: rows are not objects`;
  }
  return null;
}

// --------------------------------------------------------------------- timestamps
//: YONEPSE timestamps are naive Nepal local time (e.g. "2026-10-19T10:17:10.72").
//: Parse as NPT (UTC+05:45). A trailing Z / explicit offset is honoured.
export function parseSourceTime(value) {
  if (typeof value !== "string" || !value.trim()) return null;
  const s = value.trim();
  const hasZone = /(Z|[+-]\d{2}:?\d{2})$/.test(s);
  const iso = s.replace(" ", "T") + (hasZone ? "" : "+05:45");
  const t = Date.parse(iso);
  return Number.isFinite(t) ? new Date(t) : null;
}

export function newestIso(values) {
  let best = null;
  for (const v of values) {
    const d = parseSourceTime(v);
    if (d && (!best || d > best)) best = d;
  }
  return best ? best.toISOString() : null;
}

/** The newest source-supplied timestamp across the fetched datasets. */
export function sourceUpdatedAt(datasets) {
  const stamps = [];
  const status = datasets.status;
  if (status && typeof status.last_checked === "string") stamps.push(status.last_checked);
  const indices = datasets.indices;
  if (Array.isArray(indices)) for (const r of indices) if (r) stamps.push(r.generatedTime);
  const quotes = datasets.quotes;
  if (Array.isArray(quotes)) for (const r of quotes) if (r) stamps.push(r.last_updated);
  const manifest = datasets.ltpManifest;
  if (manifest && typeof manifest.updatedAt === "string") stamps.push(manifest.updatedAt);
  return newestIso(stamps);
}

//: Freshness vocabulary, deliberately identical in spirit to megatool/live.py so
//: the Worker and the Python backend describe the source the same way.
export const LIVE_MAX_SECONDS = 30;
export const CLOSED_LAST_CLOSE_SECONDS = 3 * 24 * 3600;
export const HISTORICAL_SECONDS = 5 * 24 * 3600;

export function freshnessLabel(ageSeconds, isOpen, publishCadenceSeconds = 3600) {
  if (ageSeconds == null || !Number.isFinite(ageSeconds)) return "unknown";
  if (ageSeconds > HISTORICAL_SECONDS) return "historical";
  if (isOpen === false && ageSeconds <= CLOSED_LAST_CLOSE_SECONDS) return "last-close";
  if (ageSeconds <= LIVE_MAX_SECONDS) return "live";
  const window = Math.max(publishCadenceSeconds * 1.5, 90);
  if (ageSeconds <= window) return "delayed";
  return "stale";
}

// --------------------------------------------------------------------- dedupe
/**
 * Decide what a run means, given the previous snapshot metadata.
 *
 * "unchanged" is a normal outcome: YONEPSE publishes hourly, so most
 * 30-minute runs re-read the same payload. It is NOT a failure, and it must
 * not be recorded as one — during a market holiday nothing changes at all.
 */
export function classifyRun(prev, sourceAt, isOpen) {
  if (!sourceAt) return { changed: true, reason: "no-source-timestamp" };
  if (!prev || !prev.source_updated_at) return { changed: true, reason: "first-run" };
  if (prev.source_updated_at !== sourceAt) return { changed: true, reason: "source-advanced" };
  if (isOpen === false) return { changed: false, reason: "closed-unchanged" };
  return { changed: false, reason: "unchanged" };
}

// --------------------------------------------------------------------- snapshot
/** A small, public snapshot. NEVER the full historical dataset. */
export function compactSnapshot(datasets, meta) {
  const quotes = Array.isArray(datasets.quotes) ? datasets.quotes : [];
  const indices = Array.isArray(datasets.indices) ? datasets.indices : [];
  const history = normaliseHistory(datasets.history);
  const summary = Array.isArray(datasets.summary) ? datasets.summary : [];
  return {
    version: 1,
    market: "NEPSE",
    currency: "NPR",
    source: "yonepse",
    source_base: YONEPSE_BASE,
    retrieved_at: meta.retrieved_at,
    source_updated_at: meta.source_updated_at,
    origin: meta.origin ?? null,
    is_open: datasets.status ? datasets.status.is_open : null,
    quote_count: quotes.length,
    missing_price: quotes.filter((q) => q && (q.ltp == null || q.ltp === "")).length,
    indices: indices.map((r) => ({
      index: r.index ?? r.indexName ?? null,
      close: r.close ?? r.currentValue ?? null,
      perChange: r.perChange ?? null,
      generatedTime: r.generatedTime ?? null,
    })),
    summary: summary.map((r) => ({ detail: r.detail ?? null, value: r.value ?? null })),
    history_latest: history.length ? history[history.length - 1] : null,
    history_count: history.length,
    ltp_manifest: datasets.ltpManifest ?? null,
  };
}

/** `history.json` is documented as {columns,rows} but has also been seen as a
 *  list of row objects; accept both and return a list of plain objects. */
export function normaliseHistory(history) {
  if (Array.isArray(history)) return history.filter((r) => r && typeof r === "object");
  if (history && Array.isArray(history.columns) && Array.isArray(history.rows)) {
    return history.rows.map((row) => {
      const o = {};
      history.columns.forEach((c, i) => (o[c] = row[i]));
      return o;
    });
  }
  return [];
}

export function mergeMetadata(prev, run) {
  const base = prev && typeof prev === "object" ? prev : {};
  return {
    ...base,
    last_checked_at: run.retrieved_at,
    last_success_at: run.ok ? run.retrieved_at : base.last_success_at ?? null,
    last_failure_at: run.ok ? base.last_failure_at ?? null : run.retrieved_at,
    last_failure_reason: run.ok ? null : run.reason ?? "unknown",
    last_run_reason: run.reason ?? null,
    source_updated_at: run.ok ? run.source_updated_at : base.source_updated_at ?? null,
    is_open: run.ok ? run.is_open : base.is_open ?? null,
    freshness: run.freshness ?? base.freshness ?? "unknown",
    quote_count: run.ok ? run.quote_count : base.quote_count ?? null,
    consecutive_failures: run.ok ? 0 : (base.consecutive_failures ?? 0) + 1,
    runs: (base.runs ?? 0) + 1,
  };
}
