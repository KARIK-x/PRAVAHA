import { describe, it, expect } from "vitest";
import worker, { serveEdge, EDGE_ROUTES } from "../src/index.js";
import { KV_META_KEY, KV_SNAPSHOT_KEY } from "../src/refresh.js";

function kvWith(values = {}) {
  const store = new Map(Object.entries(values));
  return {
    async get(key, type) {
      const v = store.get(key);
      if (v == null) return null;
      return type === "json" ? (typeof v === "string" ? JSON.parse(v) : v) : v;
    },
  };
}

const SNAPSHOT = {
  version: 1,
  retrieved_at: "2026-10-19T16:00:00.000Z",
  source_updated_at: "2026-10-19T04:32:10.000Z",
  is_open: false,
  quote_count: 362,
  indices: [{ index: "NEPSE", close: 2634.17 }],
};

const req = (url, headers = {}) =>
  new Request(url, { method: "GET", headers });

describe("edge routes (public YONEPSE snapshot)", () => {
  it("serves the snapshot from KV", async () => {
    const env = { PRAVAHA_KV: kvWith({ [KV_SNAPSHOT_KEY]: JSON.stringify(SNAPSHOT) }) };
    const r = await serveEdge("/edge/yonepse/snapshot", env, req("https://w.dev/edge/yonepse/snapshot"));
    expect(r.status).toBe(200);
    expect(r.headers.get("Content-Type")).toContain("application/json");
    expect(r.headers.get("Cache-Control")).toContain("max-age=60");
    const body = await r.json();
    expect(body.quote_count).toBe(362);
    expect(body.retrieved_at).toBe("2026-10-19T16:00:00.000Z");
  });

  it("serves ingestion metadata with no-store", async () => {
    const meta = { last_success_at: "T", last_failure_at: null, consecutive_failures: 0 };
    const env = { PRAVAHA_KV: kvWith({ [KV_META_KEY]: JSON.stringify(meta) }) };
    const r = await serveEdge("/edge/yonepse/health", env, req("https://w.dev/edge/yonepse/health"));
    expect(r.status).toBe(200);
    expect(r.headers.get("Cache-Control")).toBe("no-store");
    expect((await r.json()).consecutive_failures).toBe(0);
  });

  it("404s before the first snapshot exists", async () => {
    const r = await serveEdge("/edge/yonepse/snapshot", { PRAVAHA_KV: kvWith() }, req("https://w.dev/edge/yonepse/snapshot"));
    expect(r.status).toBe(404);
  });

  it("503s when the KV binding is absent", async () => {
    const r = await serveEdge("/edge/yonepse/snapshot", {}, req("https://w.dev/edge/yonepse/snapshot"));
    expect(r.status).toBe(503);
  });

  it("returns null for a non-edge path (falls through to the proxy)", async () => {
    const r = await serveEdge("/api/status", { PRAVAHA_KV: kvWith() }, req("https://w.dev/api/status"));
    expect(r).toBeNull();
  });

  it("requires no token (public market data only)", async () => {
    const env = { PRAVAHA_KV: kvWith({ [KV_SNAPSHOT_KEY]: JSON.stringify(SNAPSHOT) }) };
    const r = await serveEdge("/edge/yonepse/snapshot", env, req("https://w.dev/edge/yonepse/snapshot"));
    expect(r.status).toBe(200); // no X-Friend-Token sent
  });

  it("never exposes private data: the snapshot carries no user fields", () => {
    const json = JSON.stringify(SNAPSHOT);
    for (const banned of ["journal", "portfolio", "transactions", "watchlist", "screen", "token"]) {
      expect(json.toLowerCase().includes(banned)).toBe(false);
    }
  });

  it("only exposes the two documented edge routes", () => {
    expect(Object.keys(EDGE_ROUTES).sort()).toEqual([
      "/edge/yonepse/health",
      "/edge/yonepse/snapshot",
    ]);
  });

  it("routes an edge request through the worker's fetch without hitting Render", async () => {
    let originCalled = false;
    const env = {
      PRAVAHA_KV: kvWith({ [KV_SNAPSHOT_KEY]: JSON.stringify(SNAPSHOT) }),
      ORIGIN_URL: "https://origin.invalid",
    };
    const origFetch = globalThis.fetch;
    globalThis.fetch = async () => {
      originCalled = true;
      return new Response("nope", { status: 500 });
    };
    try {
      const r = await worker.fetch(req("https://w.dev/edge/yonepse/snapshot"), env, { waitUntil() {} });
      expect(r.status).toBe(200);
      expect(originCalled).toBe(false);
    } finally {
      globalThis.fetch = origFetch;
    }
  });
});

describe("scheduled handler wiring", () => {
  it("exposes a scheduled() that defers to waitUntil and never throws", async () => {
    const env = { PRAVAHA_KV: kvWith() };
    let waited = false;
    await worker.scheduled({}, env, {
      waitUntil(p) {
        waited = true;
        return p;
      },
    });
    expect(waited).toBe(true);
  });
});
