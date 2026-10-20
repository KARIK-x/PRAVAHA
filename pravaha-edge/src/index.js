import {
  isCacheable,
  isDenied,
  tokenPresent,
  ttlFor,
  corsHeaders,
} from "./logic.js";
import { handleScheduled, warmOrigin, KV_META_KEY, KV_SNAPSHOT_KEY } from "./refresh.js";

//: Public, read-only edge routes for the scheduled YONEPSE refresh. They serve
//: only public market data (never a private record) and are cached briefly.
export const EDGE_ROUTES = {
  "/edge/yonepse/snapshot": { key: KV_SNAPSHOT_KEY, ttl: 60 },
  "/edge/yonepse/health": { key: KV_META_KEY, ttl: 0 },
};

export async function serveEdge(pathname, env, request) {
  const route = EDGE_ROUTES[pathname];
  if (!route) return null;
  const cors = corsHeaders(request.headers.get("Origin") || "", env || {});
  const kv = env && env.PRAVAHA_KV;
  if (!kv) {
    return new Response(JSON.stringify({ error: "KV binding PRAVAHA_KV is not configured" }), {
      status: 503,
      headers: { "Content-Type": "application/json", ...Object.fromEntries(cors) },
    });
  }
  const raw = await kv.get(route.key, "json");
  if (raw == null) {
    return new Response(JSON.stringify({ error: "no snapshot yet", key: route.key }), {
      status: 404,
      headers: { "Content-Type": "application/json", ...Object.fromEntries(cors) },
    });
  }
  const headers = new Headers(cors);
  headers.set("Content-Type", "application/json");
  headers.set("X-Pravaha-Edge", "kv");
  headers.set(
    "Cache-Control",
    route.ttl > 0 ? `public, max-age=${route.ttl}` : "no-store"
  );
  return new Response(JSON.stringify(raw), { status: 200, headers });
}

export default {
  // Cron Trigger entry point (see [triggers] in wrangler.toml).
  async scheduled(event, env, ctx) {
    // Two independent jobs: ingest fresh public data, and keep the Python
    // origin warm so the next user request is not a 30-second cold start.
    // Neither can reject the other; allSettled never throws.
    ctx.waitUntil(Promise.allSettled([
      handleScheduled(event, env, ctx),
      warmOrigin(env),
    ]));
  },

  async fetch(request, env, ctx) {
    const earlyUrl = new URL(request.url);
    if (request.method === "GET" && EDGE_ROUTES[earlyUrl.pathname]) {
      return serveEdge(earlyUrl.pathname, env, request);
    }

    // Static frontend (Cloudflare deployment). `/api/*` and `/edge/*` are
    // always handled below; everything else is served from the asset bundle.
    // Netlify remains a separate, working deployment of the same files.
    if (env && env.ASSETS && !earlyUrl.pathname.startsWith("/api/")
        && !earlyUrl.pathname.startsWith("/edge/")) {
      const asset = await env.ASSETS.fetch(request);
      if (asset.status !== 404) return asset;
      const indexUrl = new URL("/index.html", earlyUrl);
      return env.ASSETS.fetch(new Request(indexUrl.toString(), request));
    }

    const url = new URL(request.url);
    const origin = (env && env.ORIGIN_URL) || "https://pravaha-hkwt.onrender.com";
    const originBase = new URL(origin);
    const originUrl = new URL(url.pathname + url.search, origin);
    const cors = corsHeaders(request.headers.get("Origin") || "", env || {});

    // CORS preflight
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: cors });
    }

    const cache = caches.default;
    const cacheKey = new Request(originUrl.toString(), { method: "GET" });
    const canCache = isCacheable(request.method, url.pathname) && tokenPresent(request.headers);

    // Serve from cache (only if a friend token is present)
    if (canCache) {
      const cached = await cache.match(cacheKey);
      if (cached) {
        const resp = new Response(cached.body, cached);
        cors.forEach((v, k) => { if (!resp.headers.has(k)) resp.headers.set(k, v); });
        resp.headers.set("X-Pravaha-Cache", "HIT");
        return resp;
      }
    }

    // Forward to Render (preserve auth headers)
    const fwdHeaders = new Headers(request.headers);
    fwdHeaders.set("Host", originBase.host);
    fwdHeaders.delete("connection");

    let originResp;
    try {
      originResp = await fetch(originUrl.toString(), {
        method: request.method,
        headers: fwdHeaders,
        body: ["GET", "HEAD"].includes(request.method) ? undefined : request.body,
        redirect: "manual",
      });
    } catch (err) {
      const r = new Response("Bad gateway", { status: 502, headers: cors });
      r.headers.set("X-Pravaha-Cache", "ERROR");
      return r;
    }

    // Cache eligible successful GETs (clone so origin body remains readable)
    if (canCache && originResp.ok && request.method === "GET") {
      const cc = originResp.headers.get("Cache-Control") || "";
      if (!/no-store|private/i.test(cc)) {
        const finalTtl = ttlFor(url.pathname, Number(env && env.DEFAULT_CACHE_TTL) || 60);
        const forCache = originResp.clone();
        const cacheHeaders = new Headers(forCache.headers);
        cacheHeaders.set("Cache-Control", `public, max-age=${finalTtl}`);
        cacheHeaders.delete("Set-Cookie");
        const toCache = new Response(forCache.body, {
          status: forCache.status,
          statusText: forCache.statusText,
          headers: cacheHeaders,
        });
        ctx.waitUntil(cache.put(cacheKey, toCache));

        const out = new Response(originResp.body, originResp);
        cors.forEach((v, k) => { if (!out.headers.has(k)) out.headers.set(k, v); });
        out.headers.set("X-Pravaha-Cache", "MISS");
        out.headers.set("Cache-Control", `public, max-age=${finalTtl}`);
        return out;
      }
    }

    // Pass-through (no cache)
    const out = new Response(originResp.body, originResp);
    cors.forEach((v, k) => { if (!out.headers.has(k)) out.headers.set(k, v); });
    out.headers.set("X-Pravaha-Cache", "BYPASS");
    return out;
  },
};
