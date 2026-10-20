import { describe, it, expect } from "vitest";
import { warmOrigin } from "../src/refresh.js";
import { isCacheable, ttlFor, allowedOrigin } from "../src/logic.js";
import worker from "../src/index.js";

function req(url, init = {}) {
  return new Request(url, init);
}

describe("warmOrigin (keeps Render's free instance awake)", () => {
  it("calls the public health route and reports success", async () => {
    let called = null;
    const out = await warmOrigin(
      { ORIGIN_URL: "https://render.example/" },
      { fetchImpl: async (url) => { called = url; return { ok: true, status: 200 }; } }
    );
    expect(called).toBe("https://render.example/api/health");
    expect(out.ok).toBe(true);
    expect(out.status).toBe(200);
  });

  it("never throws when the origin is down", async () => {
    const out = await warmOrigin(
      { ORIGIN_URL: "https://render.example" },
      { fetchImpl: async () => { throw new Error("connection refused"); } }
    );
    expect(out.ok).toBe(false);
    expect(out.reason).toContain("connection refused");
  });

  it("skips cleanly when no origin is configured", async () => {
    const out = await warmOrigin({});
    expect(out.ok).toBe(false);
    expect(out.skipped).toBe("no ORIGIN_URL");
  });

  it("is wired into scheduled() through waitUntil", async () => {
    let waited = false;
    await worker.scheduled({}, { ORIGIN_URL: "https://render.example" }, {
      waitUntil(p) { waited = true; return p; },
    });
    expect(waited).toBe(true);
  });
});

describe("CORS for local development", () => {
  it("allows any loopback port but not a remote origin", () => {
    expect(allowedOrigin("http://127.0.0.1:10000", {})).toBe("http://127.0.0.1:10000");
    expect(allowedOrigin("http://localhost:1234", {})).toBe("http://localhost:1234");
    expect(allowedOrigin("https://evil.example", {})).toBe(null);
    expect(allowedOrigin("https://pravahanepse.netlify.app", {
      FRONTEND_ORIGIN: "https://pravahanepse.netlify.app",
    })).toBe("https://pravahanepse.netlify.app");
  });
});

describe("edge cache for the public BABA read surface", () => {
  it("caches the component catalog, research catalog and range forecast", () => {
    expect(isCacheable("GET", "/api/baba/components")).toBe(true);
    expect(isCacheable("GET", "/api/baba/research/catalog")).toBe(true);
    expect(isCacheable("GET", "/api/baba/volatility/NABIL")).toBe(true);
  });

  it("never caches report jobs, downloads or exports", () => {
    expect(isCacheable("GET", "/api/baba/research/jobs")).toBe(false);
    expect(isCacheable("GET", "/api/baba/research/jobs/abc/download/pdf")).toBe(false);
    expect(isCacheable("GET", "/api/baba/report/export")).toBe(false);
    expect(isCacheable("POST", "/api/baba/research/jobs")).toBe(false);
  });

  it("gives the catalogs a longer TTL than live quotes", () => {
    expect(ttlFor("/api/baba/research/catalog")).toBe(600);
    expect(ttlFor("/api/baba/volatility/NABIL")).toBe(300);
  });
});

describe("static assets (Cloudflare-hosted frontend)", () => {
  it("serves an asset and falls back to index.html for unknown paths", async () => {
    const seen = [];
    const env = {
      ASSETS: {
        async fetch(request) {
          const u = new URL(request.url);
          seen.push(u.pathname);
          if (u.pathname === "/") {
            return new Response("<html>PRAVAHA</html>", {
              headers: { "Content-Type": "text/html" },
            });
          }
          if (u.pathname === "/index.html") {
            return new Response("<html>INDEX</html>", {
              headers: { "Content-Type": "text/html" },
            });
          }
          return new Response("not found", { status: 404 });
        },
      },
    };
    const home = await worker.fetch(req("https://edge.example/"), env, { waitUntil() {} });
    expect(home.status).toBe(200);
    expect(await home.text()).toContain("PRAVAHA");

    const deep = await worker.fetch(req("https://edge.example/research"), env, { waitUntil() {} });
    expect(deep.status).toBe(200);
    expect(await deep.text()).toContain("INDEX");
    expect(seen).toContain("/research");
  });

  it("does not route /api paths to the asset bundle", async () => {
    let assetCalls = 0;
    const env = {
      ORIGIN_URL: "https://render.example",
      ASSETS: { async fetch() { assetCalls += 1; return new Response("asset"); } },
    };
    const original = globalThis.fetch;
    const originalCaches = globalThis.caches;
    globalThis.caches = { default: { async match() { return undefined; }, async put() {} } };
    globalThis.fetch = async () => new Response(JSON.stringify({ ok: true }), {
      status: 200, headers: { "Content-Type": "application/json" },
    });
    try {
      const r = await worker.fetch(req("https://edge.example/api/health"), env, { waitUntil() {} });
      expect(r.status).toBe(200);
      expect(assetCalls).toBe(0);
    } finally {
      globalThis.fetch = original;
      globalThis.caches = originalCaches;
    }
  });
});
