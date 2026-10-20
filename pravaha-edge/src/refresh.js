// Scheduled YONEPSE refresh. Runs on the Cloudflare Cron Trigger.
//
// Guarantees:
//   * Only documented public JSON is read; no auth, no scraping.
//   * Bounded timeout + bounded retries; a slow source cannot hang the run.
//   * Every payload is validated before anything is stored.
//   * A failed fetch NEVER overwrites the stored snapshot (last good is kept).
//   * "Unchanged" is a normal outcome (YONEPSE publishes hourly), and during a
//     market holiday unchanged data is explicitly NOT a failure.
//   * LTP snapshots are summarised, never converted into OHLCV candles.

import {
  DATASETS,
  YONEPSE_BASES,
  classifyRun,
  compactSnapshot,
  freshnessLabel,
  isMarketWindow,
  mergeMetadata,
  nptParts,
  sourceUpdatedAt,
  validateDataset,
} from "./yonepse.js";

export const KV_SNAPSHOT_KEY = "yonepse:snapshot";
export const KV_META_KEY = "yonepse:meta";

//: A snapshot is only written when these succeed. The rest are recorded as
//: missing but do not block the write.
export const CRITICAL = ["status", "indices", "quotes"];

//: YONEPSE publishes ~hourly; freshness is judged against that cadence.
export const PUBLISH_CADENCE_SECONDS = 3600;

const DEFAULT_TIMEOUT_MS = 8000;
const DEFAULT_RETRIES = 2;

export async function fetchJson(
  url,
  { fetchImpl = fetch, timeoutMs = DEFAULT_TIMEOUT_MS, retries = DEFAULT_RETRIES, sleep } = {}
) {
  const wait = sleep || ((ms) => new Promise((r) => setTimeout(r, ms)));
  let lastErr = null;
  for (let attempt = 0; attempt <= retries; attempt++) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort("timeout"), timeoutMs);
    try {
      const resp = await fetchImpl(url, {
        signal: ctrl.signal,
        headers: { Accept: "application/json", "User-Agent": "PRAVAHA-edge/0.1" },
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const text = await resp.text();
      if (!text) throw new Error("empty body");
      return JSON.parse(text);
    } catch (err) {
      lastErr = err;
      if (attempt < retries) await wait(300 * (attempt + 1));
    } finally {
      clearTimeout(timer);
    }
  }
  throw new Error(`fetch failed for ${url}: ${lastErr && lastErr.message ? lastErr.message : lastErr}`);
}

/**
 * Fetch one dataset, trying each base in order (raw content first, then the
 * Pages mirror). Returns `{data, origin}`; throws only when every base failed.
 */
export async function fetchDataset(path, bases, opts = {}) {
  let lastErr = null;
  for (const base of bases) {
    const url = `${String(base).replace(/\/+$/, "")}/${path}`;
    try {
      const data = await fetchJson(url, opts);
      return { data, origin: base };
    } catch (err) {
      lastErr = err;
    }
  }
  throw lastErr || new Error(`no base could serve ${path}`);
}

/** Read the stored metadata (tolerates a missing/corrupt value). */
export async function readMeta(kv) {
  if (!kv) return null;
  try {
    const raw = await kv.get(KV_META_KEY, "json");
    return raw && typeof raw === "object" ? raw : null;
  } catch {
    return null;
  }
}

/**
 * One scheduled run.
 *
 * @returns a plain result object (also written to KV as metadata).
 */
export async function runScheduledRefresh(env = {}, opts = {}) {
  const now = opts.now || new Date();
  const kv = opts.kv || env.PRAVAHA_KV || null;
  const force = !!opts.force;
  // Raw content first, Pages mirror second (see YONEPSE_BASES).
  const bases = env.YONEPSE_BASES
    ? String(env.YONEPSE_BASES).split(",").map((s) => s.trim()).filter(Boolean)
    : YONEPSE_BASES;
  const retrievedAt = now.toISOString();

  const outsideWindow = !isMarketWindow(now);
  if (outsideWindow && !force) {
    // Deliberately quiet: no source request, no KV write. The last snapshot and
    // its timestamps stay as they are, so a closed market is not reported as a
    // problem.
    return {
      ok: true,
      skipped: "outside-market-window",
      retrieved_at: retrievedAt,
      npt: nptParts(now).iso,
    };
  }

  const datasets = {};
  const failed = [];
  const missing = [];

  const origins = new Set();
  for (const ds of DATASETS) {
    try {
      const { data, origin } = await fetchDataset(ds.path, bases, opts);
      origins.add(origin);
      const problem = validateDataset(ds.path, data, ds.shape);
      if (problem) {
        failed.push(problem);
        missing.push(ds.key);
        continue;
      }
      datasets[ds.key] = data;
    } catch (err) {
      failed.push(`${ds.path}: ${err && err.message ? err.message : err}`);
      missing.push(ds.key);
    }
  }

  const prev = await readMeta(kv);
  const criticalFailed = CRITICAL.filter((k) => missing.includes(k));
  const sourceAt = sourceUpdatedAt(datasets);
  const isOpen = datasets.status ? datasets.status.is_open : null;
  const ageSeconds = sourceAt ? (now.getTime() - Date.parse(sourceAt)) / 1000 : null;
  const freshness = freshnessLabel(ageSeconds, isOpen, PUBLISH_CADENCE_SECONDS);

  if (criticalFailed.length) {
    // The source request failed for something essential: keep the last good
    // snapshot untouched and record the failure.
    const run = {
      ok: false,
      reason: `critical datasets failed: ${criticalFailed.join(", ")}`,
      failures: failed,
      retrieved_at: retrievedAt,
    };
    const meta = mergeMetadata(prev, run);
    if (kv) await kv.put(KV_META_KEY, JSON.stringify(meta));
    return { ...run, meta };
  }

  const verdict = classifyRun(prev, sourceAt, isOpen);
  const run = {
    ok: true,
    reason: verdict.reason,
    changed: verdict.changed,
    retrieved_at: retrievedAt,
    source_updated_at: sourceAt,
    is_open: isOpen,
    freshness,
    origin: [...origins],
    quote_count: Array.isArray(datasets.quotes) ? datasets.quotes.length : null,
    missing_datasets: missing,
    failures: failed,
  };

  if (verdict.changed && kv) {
    const snapshot = compactSnapshot(datasets, run);
    await kv.put(KV_SNAPSHOT_KEY, JSON.stringify(snapshot));
  }

  const meta = mergeMetadata(prev, run);
  if (kv) await kv.put(KV_META_KEY, JSON.stringify(meta));
  return { ...run, meta };
}

/** The `scheduled()` entry point: never throws into the runtime. */
export async function handleScheduled(event, env, ctx, opts = {}) {
  try {
    const result = await runScheduledRefresh(env, opts);
    return result;
  } catch (err) {
    // A thrown error here would be retried by the platform and could mask the
    // cause; record it and return normally.
    const failure = {
      ok: false,
      reason: `scheduled run threw: ${err && err.message ? err.message : err}`,
      retrieved_at: new Date().toISOString(),
    };
    try {
      const kv = env && env.PRAVAHA_KV;
      if (kv) {
        const prev = await readMeta(kv);
        await kv.put(KV_META_KEY, JSON.stringify(mergeMetadata(prev, failure)));
      }
    } catch {
      /* a logging failure must not mask the original */
    }
    return failure;
  }
}

/**
 * Keep the authoritative Python origin warm.
 *
 * Render's free plan spins a service down after ~15 minutes of inactivity, and
 * the next request then waits 20-60 seconds. A cron tick that fetches the
 * always-public `/api/health` every 10 minutes prevents that cold start without
 * changing Render's configuration. The call is bounded, tolerant of failure and
 * never throws: a failed warm-up must not be reported as an ingestion failure.
 */
export async function warmOrigin(env = {}, opts = {}) {
  const origin = String((env && env.ORIGIN_URL) || "").replace(/\/+$/, "");
  if (!origin) return { ok: false, skipped: "no ORIGIN_URL" };
  const fetchImpl = opts.fetchImpl || fetch;
  // A sleeping Render instance can take 30-60s to answer its first request.
  // Aborting earlier would make the keep-warm ping useless on the one tick
  // that matters; the cron's wall-clock budget is much larger than this.
  const timeoutMs = Number(opts.timeoutMs || 60000);
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort("timeout"), timeoutMs);
  const started = Date.now();
  try {
    const resp = await fetchImpl(`${origin}/api/health`, {
      method: "GET",
      signal: ctrl.signal,
      headers: { Accept: "application/json", "User-Agent": "PRAVAHA-edge-warm/0.1" },
      redirect: "manual",
    });
    return {
      ok: !!resp.ok,
      status: resp.status,
      elapsed_ms: Date.now() - started,
      at: new Date().toISOString(),
    };
  } catch (err) {
    return {
      ok: false,
      reason: err && err.message ? err.message : String(err),
      elapsed_ms: Date.now() - started,
      at: new Date().toISOString(),
    };
  } finally {
    clearTimeout(timer);
  }
}
