import { describe, it, expect } from "vitest";
import {
  runScheduledRefresh,
  handleScheduled,
  fetchJson,
  KV_META_KEY,
  KV_SNAPSHOT_KEY,
  CRITICAL,
} from "../src/refresh.js";
import { YONEPSE_BASE, YONEPSE_RAW_BASE, YONEPSE_BASES } from "../src/yonepse.js";

// ---- fixtures --------------------------------------------------------------
const MONDAY_MARKET = new Date("2026-10-19T05:30:00Z"); // 11:15 NPT, Mon
const MONDAY_PREOPEN = new Date("2026-10-19T02:00:00Z"); // 07:45 NPT, Mon

function payloads(over = {}) {
  return {
    "data/market/status.json": { is_open: true, last_checked: "2026-10-19T11:10:00" },
    "data/market/indices.json": [
      { index: "NEPSE", close: 2634.17, perChange: 0.31, generatedTime: "2026-10-19T11:00:00" },
    ],
    "data/market/summary.json": [{ detail: "Total Turnover Rs:", value: 123 }],
    "data/market/sector_indices.json": [{ indexCode: "BANK", indexName: "Banking Index" }],
    "data/market/history.json": { columns: ["businessDate"], rows: [["2026-10-16"]] },
    "data/ltp/manifest.json": { latestDate: "2026-10-16", latestStatus: "final" },
    "data/nepse_data.json": [{ symbol: "NABIL", ltp: 547, last_updated: "2026-10-19T11:05:00" }],
    ...over,
  };
}

function mockFetch(over = {}, { failPaths = [], invalidPaths = [], failBases = [], status = 200 } = {}) {
  const P = payloads(over);
  const calls = [];
  const impl = async (url) => {
    const u = String(url);
    const path = Object.keys(P).find((k) => u.endsWith(k));
    calls.push(u);
    // A base listed in failBases is unreachable (simulates the Pages mirror
    // being stale/down so the raw base must answer).
    if (failBases.some((b) => u.startsWith(b))) return { ok: false, status: 503, text: async () => "" };
    if (failPaths.includes(path)) return { ok: false, status: 500, text: async () => "" };
    if (invalidPaths.includes(path)) return { ok: true, status, text: async () => "{not json" };
    const body = P[path];
    if (body === undefined) return { ok: false, status: 404, text: async () => "" };
    return { ok: true, status, text: async () => JSON.stringify(body) };
  };
  impl.calls = calls;
  return impl;
}

function mockKV() {
  const store = new Map();
  const puts = [];
  return {
    _store: store,
    _puts: puts,
    async get(key, type) {
      const v = store.get(key);
      if (v == null) return null;
      return type === "json" ? JSON.parse(v) : v;
    },
    async put(key, value) {
      store.set(key, value);
      puts.push(key);
    },
    putsFor(key) {
      return puts.filter((k) => k === key).length;
    },
  };
}

const noSleep = async () => {};

// ---- tests -----------------------------------------------------------------
describe("scheduling / market awareness", () => {
  it("skips the source entirely outside the NPT market window", async () => {
    const f = mockFetch();
    const kv = mockKV();
    const out = await runScheduledRefresh({ PRAVAHA_KV: kv }, {
      now: MONDAY_PREOPEN,
      fetchImpl: f,
      sleep: noSleep,
    });
    expect(out.skipped).toBe("outside-market-window");
    expect(f.calls).toHaveLength(0); // no upstream request
    expect(kv._puts).toHaveLength(0); // no write
  });

  it("runs inside the market window", async () => {
    const f = mockFetch();
    const kv = mockKV();
    const out = await runScheduledRefresh({ PRAVAHA_KV: kv }, {
      now: MONDAY_MARKET,
      fetchImpl: f,
      sleep: noSleep,
    });
    expect(out.ok).toBe(true);
    expect(out.changed).toBe(true);
    expect(out.reason).toBe("first-run");
    expect(f.calls.length).toBeGreaterThanOrEqual(CRITICAL.length);
  });
});

describe("successful fetch", () => {
  it("stores a snapshot and metadata, separating the two timestamps", async () => {
    const kv = mockKV();
    const out = await runScheduledRefresh({ PRAVAHA_KV: kv }, {
      now: MONDAY_MARKET,
      fetchImpl: mockFetch(),
      sleep: noSleep,
    });
    expect(kv.putsFor(KV_SNAPSHOT_KEY)).toBe(1);
    const snap = await kv.get(KV_SNAPSHOT_KEY, "json");
    expect(snap.retrieved_at).toBe(MONDAY_MARKET.toISOString());
    expect(snap.source_updated_at).toBe("2026-10-19T05:25:00.000Z"); // 11:10 NPT
    expect(snap.is_open).toBe(true);
    expect(snap.quote_count).toBe(1);
    const meta = await kv.get(KV_META_KEY, "json");
    expect(meta.last_success_at).toBe(MONDAY_MARKET.toISOString());
    expect(meta.last_checked_at).toBe(MONDAY_MARKET.toISOString());
    expect(meta.consecutive_failures).toBe(0);
  });

  it("records an unchanged payload without rewriting the snapshot", async () => {
    const kv = mockKV();
    const f = mockFetch();
    await runScheduledRefresh({ PRAVAHA_KV: kv }, { now: MONDAY_MARKET, fetchImpl: f, sleep: noSleep });
    const out = await runScheduledRefresh({ PRAVAHA_KV: kv }, {
      now: new Date(MONDAY_MARKET.getTime() + 30 * 60 * 1000),
      fetchImpl: f,
      sleep: noSleep,
    });
    expect(out.ok).toBe(true);
    expect(out.changed).toBe(false);
    expect(out.reason).toBe("unchanged");
    expect(kv.putsFor(KV_SNAPSHOT_KEY)).toBe(1); // still only the first write
  });

  it("treats unchanged data during a market holiday as normal, not a failure", async () => {
    const kv = mockKV();
    const f = mockFetch({ "data/market/status.json": { is_open: false, last_checked: "2026-10-19T11:10:00" } });
    await runScheduledRefresh({ PRAVAHA_KV: kv }, { now: MONDAY_MARKET, fetchImpl: f, sleep: noSleep });
    const out = await runScheduledRefresh({ PRAVAHA_KV: kv }, {
      now: new Date(MONDAY_MARKET.getTime() + 30 * 60 * 1000),
      fetchImpl: f,
      sleep: noSleep,
    });
    expect(out.ok).toBe(true);
    expect(out.reason).toBe("closed-unchanged");
    const meta = await kv.get(KV_META_KEY, "json");
    expect(meta.last_failure_reason).toBeNull();
    expect(meta.consecutive_failures).toBe(0);
  });

  it("labels a closed market's observation last-close (never stale)", async () => {
    const kv = mockKV();
    const out = await runScheduledRefresh({ PRAVAHA_KV: kv }, {
      now: MONDAY_MARKET,
      fetchImpl: mockFetch({
        "data/market/status.json": { is_open: false, last_checked: "2026-10-19T11:10:00" },
      }),
      sleep: noSleep,
    });
    expect(out.freshness).toBe("last-close");
  });
});

describe("failure handling", () => {
  it("keeps the last good snapshot when a critical dataset fails", async () => {
    const kv = mockKV();
    await runScheduledRefresh({ PRAVAHA_KV: kv }, {
      now: MONDAY_MARKET,
      fetchImpl: mockFetch(),
      sleep: noSleep,
    });
    const before = await kv.get(KV_SNAPSHOT_KEY, "json");
    const out = await runScheduledRefresh({ PRAVAHA_KV: kv }, {
      now: new Date(MONDAY_MARKET.getTime() + 30 * 60 * 1000),
      fetchImpl: mockFetch({}, { failPaths: ["data/market/status.json"] }),
      sleep: noSleep,
    });
    expect(out.ok).toBe(false);
    expect(out.reason).toMatch(/critical datasets failed: status/);
    expect(kv.putsFor(KV_SNAPSHOT_KEY)).toBe(1); // NOT overwritten
    expect(await kv.get(KV_SNAPSHOT_KEY, "json")).toEqual(before);
    const meta = await kv.get(KV_META_KEY, "json");
    expect(meta.last_failure_at).toBeTruthy();
    expect(meta.consecutive_failures).toBe(1);
    expect(meta.last_success_at).toBe(MONDAY_MARKET.toISOString());
  });

  it("rejects an unparseable payload and does not store it", async () => {
    const kv = mockKV();
    const out = await runScheduledRefresh({ PRAVAHA_KV: kv }, {
      now: MONDAY_MARKET,
      fetchImpl: mockFetch({}, { invalidPaths: ["data/market/indices.json"] }),
      sleep: noSleep,
    });
    expect(out.ok).toBe(false);
    expect(out.reason).toMatch(/critical datasets failed: indices/);
    expect(kv.putsFor(KV_SNAPSHOT_KEY)).toBe(0);
  });

  it("rejects a wrong-shape payload (status without a boolean is_open)", async () => {
    const kv = mockKV();
    const out = await runScheduledRefresh({ PRAVAHA_KV: kv }, {
      now: MONDAY_MARKET,
      fetchImpl: mockFetch({ "data/market/status.json": { last_checked: "x" } }),
      sleep: noSleep,
    });
    expect(out.ok).toBe(false);
    expect(out.failures.join(" ")).toMatch(/is_open is not a boolean/);
  });

  it("survives a non-critical dataset failing and says which is missing", async () => {
    const kv = mockKV();
    const out = await runScheduledRefresh({ PRAVAHA_KV: kv }, {
      now: MONDAY_MARKET,
      fetchImpl: mockFetch({}, { failPaths: ["data/market/summary.json"] }),
      sleep: noSleep,
    });
    expect(out.ok).toBe(true);
    expect(out.missing_datasets).toContain("summary");
  });
});

describe("raw content first, Pages mirror as fallback", () => {
  it("reads the raw repository content by default", async () => {
    const f = mockFetch();
    const out = await runScheduledRefresh({ PRAVAHA_KV: mockKV() }, {
      now: MONDAY_MARKET,
      fetchImpl: f,
      sleep: noSleep,
    });
    expect(out.origin).toContain(YONEPSE_RAW_BASE);
    expect(f.calls.every((u) => u.startsWith(YONEPSE_RAW_BASE))).toBe(true);
  });

  it("falls back to the Pages mirror when raw is unreachable", async () => {
    const f = mockFetch({}, { failBases: [YONEPSE_RAW_BASE] });
    const out = await runScheduledRefresh({ PRAVAHA_KV: mockKV() }, {
      now: MONDAY_MARKET,
      fetchImpl: f,
      sleep: noSleep,
    });
    expect(out.ok).toBe(true);
    expect(out.origin).toContain(YONEPSE_BASE);
  });

  it("lists raw before Pages in the documented base order", () => {
    expect(YONEPSE_BASES[0]).toBe(YONEPSE_RAW_BASE);
    expect(YONEPSE_BASES[1]).toBe(YONEPSE_BASE);
  });
});

describe("bounded retries", () => {
  it("retries a failing request a bounded number of times, then gives up", async () => {
    let attempts = 0;
    const impl = async () => {
      attempts++;
      return { ok: false, status: 503, text: async () => "" };
    };
    await expect(
      fetchJson("https://example.invalid/x", { fetchImpl: impl, retries: 2, sleep: noSleep })
    ).rejects.toThrow(/HTTP 503/);
    expect(attempts).toBe(3); // 1 + 2 retries, never unbounded
  });

  it("succeeds on a later attempt", async () => {
    let n = 0;
    const impl = async () => {
      n++;
      if (n < 3) return { ok: false, status: 500, text: async () => "" };
      return { ok: true, status: 200, text: async () => '{"ok":true}' };
    };
    await expect(fetchJson("https://example.invalid/y", { fetchImpl: impl, retries: 2, sleep: noSleep }))
      .resolves.toEqual({ ok: true });
  });
});

describe("scheduled entry point", () => {
  it("never throws and records a thrown error as a failure", async () => {
    const kv = mockKV();
    const boom = async () => {
      throw new Error("kaboom");
    };
    const out = await handleScheduled({}, { PRAVAHA_KV: kv }, {}, {
      now: MONDAY_MARKET,
      fetchImpl: boom,
      sleep: noSleep,
    });
    // fetchJson wraps the throw; the critical dataset fails -> recorded
    expect(out.ok).toBe(false);
    expect(kv.putsFor(KV_META_KEY)).toBe(1);
  });

  it("returns a structured result for the runtime", async () => {
    const kv = mockKV();
    const out = await handleScheduled({}, { PRAVAHA_KV: kv }, {}, {
      now: MONDAY_MARKET,
      fetchImpl: mockFetch(),
      sleep: noSleep,
    });
    expect(out).toMatchObject({ ok: true, changed: true });
  });
});

describe("KV quotas (free tier sanity)", () => {
  it("writes at most 2 KV keys per run", async () => {
    const kv = mockKV();
    await runScheduledRefresh({ PRAVAHA_KV: kv }, {
      now: MONDAY_MARKET,
      fetchImpl: mockFetch(),
      sleep: noSleep,
    });
    expect(kv._puts.length).toBeLessThanOrEqual(2);
    // 48 runs/day * 2 = 96 writes/day, far under the 1,000/day free limit.
    expect(kv._puts.length * 48).toBeLessThan(1000);
  });

  it("does not touch KV when there is no binding (dry local run)", async () => {
    const out = await runScheduledRefresh({}, {
      now: MONDAY_MARKET,
      fetchImpl: mockFetch(),
      sleep: noSleep,
    });
    expect(out.ok).toBe(true);
  });
});
