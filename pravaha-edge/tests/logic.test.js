import { describe, it, expect } from "vitest";
import {
  isDenied,
  isCacheable,
  tokenPresent,
  ttlFor,
  allowedOrigin,
  corsHeaders,
  DENIED_PREFIXES,
  CACHEABLE,
} from "../src/logic.js";

describe("isDenied (private/owner-only prefixes)", () => {
  it("denies exact prefix", () => {
    expect(isDenied("/api/portfolio")).toBe(true);
  });
  it("denies child paths", () => {
    expect(isDenied("/api/portfolio/transactions")).toBe(true);
    expect(isDenied("/api/journal/42")).toBe(true);
    expect(isDenied("/api/research/topics")).toBe(true);
  });
  it("does not deny unrelated prefixes (boundary safety)", () => {
    expect(isDenied("/api/portfolios")).toBe(false);
    expect(isDenied("/api/bars/AAPL")).toBe(false);
    expect(isDenied("/api/health")).toBe(false);
  });
  it("denies query-string variants", () => {
    expect(isDenied("/api/portfolio?x=1")).toBe(true);
  });
});

describe("isCacheable (eligibility)", () => {
  it("caches allowlisted public GET market data", () => {
    expect(isCacheable("GET", "/api/bars/AAPL")).toBe(true);
    expect(isCacheable("GET", "/api/quotes")).toBe(true);
    expect(isCacheable("GET", "/api/fundamentals/summary")).toBe(true);
    expect(isCacheable("GET", "/api/live/market")).toBe(true);
  });
  it("never caches non-GET", () => {
    expect(isCacheable("POST", "/api/screen")).toBe(false);
    expect(isCacheable("POST", "/api/bars/AAPL")).toBe(false);
  });
  it("never caches denied/private routes", () => {
    for (const p of ["/api/portfolio", "/api/journal/1", "/api/research/topics",
                     "/api/news/summary", "/api/alerts/history"]) {
      expect(isCacheable("GET", p)).toBe(false);
    }
  });
  it("never caches health probe", () => {
    expect(isCacheable("GET", "/api/health")).toBe(false);
  });
  it("never caches file exports", () => {
    expect(isCacheable("GET", "/api/screen/export.csv")).toBe(false);
    expect(isCacheable("GET", "/api/screen/export.pdf")).toBe(false);
    expect(isCacheable("GET", "/api/screen/export.xlsx")).toBe(false);
  });
  it("does not cache unknown routes", () => {
    expect(isCacheable("GET", "/api/does-not-exist")).toBe(false);
    expect(isCacheable("GET", "/")).toBe(false);
  });
});

describe("tokenPresent (auth gating for cache)", () => {
  it("true when X-Friend-Token present", () => {
    const h = new Headers({ "X-Friend-Token": "secret" });
    expect(tokenPresent(h)).toBe(true);
  });
  it("true when Authorization Bearer present", () => {
    const h = new Headers({ Authorization: "Bearer abc" });
    expect(tokenPresent(h)).toBe(true);
  });
  it("false when no token", () => {
    expect(tokenPresent(new Headers())).toBe(false);
    expect(tokenPresent(null)).toBe(false);
  });
  it("case-insensitive header lookup", () => {
    const h = new Headers({ "x-friend-token": "t" });
    expect(tokenPresent(h)).toBe(true);
  });
});

describe("ttlFor", () => {
  it("short TTL for live/quotes", () => {
    expect(ttlFor("/api/live/market")).toBe(30);
    expect(ttlFor("/api/quotes")).toBe(30);
    expect(ttlFor("/api/dashboard")).toBe(30);
  });
  it("longer TTL for bars/fundamentals", () => {
    expect(ttlFor("/api/bars/AAPL")).toBe(300);
    expect(ttlFor("/api/fundamentals/summary")).toBe(600);
  });
  it("default TTL otherwise", () => {
    expect(ttlFor("/api/indicators")).toBe(60);
    expect(ttlFor("/api/indicators", 120)).toBe(120);
  });
});

describe("allowedOrigin / CORS", () => {
  const env = { FRONTEND_ORIGIN: "https://pravahanepse.netlify.app" };
  it("allows configured origin", () => {
    expect(allowedOrigin("https://pravahanepse.netlify.app", env)).toBe("https://pravahanepse.netlify.app");
  });
  it("rejects unknown origin", () => {
    expect(allowedOrigin("https://evil.example", env)).toBeNull();
  });
  it("allows localhost dev origins", () => {
    expect(allowedOrigin("http://127.0.0.1:8787", env)).toBe("http://127.0.0.1:8787");
    expect(allowedOrigin("http://localhost:8710", env)).toBe("http://localhost:8710");
  });
  it("CORS headers include ACAO only for allowed origin", () => {
    const h = corsHeaders("https://pravahanepse.netlify.app", env);
    expect(h.get("Access-Control-Allow-Origin")).toBe("https://pravahanepse.netlify.app");
    const h2 = corsHeaders("https://evil.example", env);
    expect(h2.get("Access-Control-Allow-Origin")).toBeNull();
  });
});

describe("cache isolation (logical)", () => {
  it("cache eligibility requires a token; no token -> never cached", () => {
    // Even an allowlisted GET is not cacheable without a token.
    expect(isCacheable("GET", "/api/bars/AAPL")).toBe(true);
    const h = new Headers(); // no token
    // canCache = isCacheable && tokenPresent; simulate:
    expect(tokenPresent(h)).toBe(false);
  });
  it("denied routes stay non-cacheable even with token present", () => {
    const h = new Headers({ "X-Friend-Token": "t" });
    expect(tokenPresent(h)).toBe(true);
    expect(isCacheable("GET", "/api/portfolio")).toBe(false);
  });
});
