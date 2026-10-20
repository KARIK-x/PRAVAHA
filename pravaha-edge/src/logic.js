// Pure, testable logic for the PRAVAHA edge Worker.
// Mirrors megatool/friend_access.py (FRIEND_ROUTES / FRIEND_DENIED_PREFIXES).
// No Cloudflare-runtime globals are required here.

export const DEFAULT_TTL = 60;

export const DENIED_PREFIXES = [
  "/api/portfolio", "/api/journal", "/api/planning", "/api/alerts",
  "/api/watchlists", "/api/experiments", "/api/screens", "/api/written-pdf",
  "/api/research", "/api/research-desk", "/api/agent", "/api/snapshots",
  "/api/query", "/api/templates", "/api/reconciliation",
  "/api/kronos/experiments", "/api/news",
  "/api/fundamentals/import", "/api/floorsheet/import",
  "/api/corporate-events/import", "/api/market-intelligence/import",
  "/api/market-intelligence/collect",
];

export const CACHEABLE = [
  /^\/api\/status$/,
  /^\/api\/sources$/,
  /^\/api\/collector\/status$/,
  /^\/api\/gonepse\/status$/,
  /^\/api\/live\/(status|market|quotes)$/,
  /^\/api\/quotes$/,
  /^\/api\/securities$/,
  /^\/api\/sectors$/,
  /^\/api\/dashboard$/,
  /^\/api\/market\/dashboard$/,
  /^\/api\/market\/ribbon$/,
  /^\/api\/quality$/,
  /^\/api\/regime(\/history)?$/,
  /^\/api\/breadth\/history$/,
  /^\/api\/seasonality\/[A-Za-z0-9._-]+$/,
  /^\/api\/indices$/,
  /^\/api\/indices\/[A-Za-z0-9 ._&()+-]+$/,
  /^\/api\/indices\/[A-Za-z0-9 ._&()+-]+\/(ohlc|structure)$/,
  /^\/api\/bars\/[A-Za-z0-9._-]+$/,
  /^\/api\/bars\/[A-Za-z0-9._-]+\/(weekly|monthly)$/,
  /^\/api\/bars\/[A-Za-z0-9._-]+\/(indicator|structure|fibonacci|levels|elliott|harmonic|patterns|candles|statistics|relative-strength|swing-workbench|volume-profile|gaps|breakouts|trailing-stop)$/,
  /^\/api\/indicators$/,
  /^\/api\/stats\/correlation$/,
  /^\/api\/screen\/presets$/,
  /^\/api\/strategies$/,
  /^\/api\/fundamentals\/summary$/,
  /^\/api\/fundamentals\/compare$/,
  /^\/api\/fundamentals\/(eps-rankings|revisions|as-of)$/,
  /^\/api\/fundamentals\/(?!import$)[A-Za-z0-9._-]+$/,
  /^\/api\/fundamentals\/[A-Za-z0-9._-]+\/(ratios|eps-growth|ttm-eps|historical-pe)$/,
  /^\/api\/floorsheet\/(sessions|summary|trend)$/,
  /^\/api\/sastoshare\/(pulse|movers|rotation|dividends)$/,
  /^\/api\/sastoshare\/(valuation|valuation-history|risk|volatility)\/[A-Za-z0-9._-]+$/,
  /^\/api\/forecast\/models$/,
  /^\/api\/catalog\/summary$/,
  /^\/api\/catalog\/[A-Za-z0-9._-]+$/,
  /^\/api\/catalog\/tool\/.+$/,
  /^\/api\/ideas$/,
  /^\/api\/ideas\/[A-Za-z0-9._-]+$/,
  /^\/api\/corporate-events$/,
  /^\/api\/corporate-events\/(calendar|coverage)$/,
  /^\/api\/market-intelligence\/(health|sources|source-health)$/,
  /^\/api\/kronos\/status$/,
  // BABA public, read-only selection metadata and computed analytics. Report
  // exports and job downloads are deliberately NOT cacheable (unmatched).
  /^\/api\/baba\/components$/,
  /^\/api\/baba\/research\/catalog$/,
  /^\/api\/baba\/volatility\/[A-Za-z0-9._-]+$/,
];

export const TTL_RULES = [
  { re: /^\/api\/live\//, ttl: 30 },
  { re: /^\/api\/market\/ribbon$/, ttl: 30 },
  { re: /^\/api\/dashboard$/, ttl: 30 },
  { re: /^\/api\/quotes$/, ttl: 30 },
  { re: /^\/api\/bars\//, ttl: 300 },
  { re: /^\/api\/fundamentals\//, ttl: 600 },
  { re: /^\/api\/indices\//, ttl: 300 },
  { re: /^\/api\/catalog\//, ttl: 600 },
  { re: /^\/api\/ideas(\/|$)/, ttl: 300 },
  { re: /^\/api\/baba\/components$/, ttl: 600 },
  { re: /^\/api\/baba\/research\/catalog$/, ttl: 600 },
  { re: /^\/api\/baba\/volatility\//, ttl: 300 },
];

export function isDenied(pathname) {
  return DENIED_PREFIXES.some(
    (p) => pathname === p || pathname.startsWith(p + "/") || pathname.startsWith(p + "?")
  );
}

export function isCacheable(method, pathname) {
  if (method !== "GET") return false;
  if (isDenied(pathname)) return false;
  if (pathname === "/api/health") return false;            // keep probes live
  if (/^\/api\/screen\/export\./.test(pathname)) return false; // no stale exports
  return CACHEABLE.some((re) => re.test(pathname));
}

export function tokenPresent(headers) {
  if (!headers || typeof headers.get !== "function") return false;
  return !!(headers.get("X-Friend-Token") || headers.get("Authorization"));
}

export function ttlFor(pathname, fallback = DEFAULT_TTL) {
  for (const r of TTL_RULES) if (r.re.test(pathname)) return r.ttl;
  return fallback;
}

export function allowedOrigin(origin, env) {
  const configured = (env && env.FRONTEND_ORIGIN ? String(env.FRONTEND_ORIGIN) : "").trim();
  const edge = (env && env.EDGE_ORIGIN ? String(env.EDGE_ORIGIN) : "").trim();
  const allowed = new Set();
  if (configured) allowed.add(configured);
  if (edge) allowed.add(edge);
  // Any loopback origin is a local development server, never a remote caller.
  // Allowing the whole loopback range avoids a browser CORS error (and a noisy
  // console) when the dev server runs on a non-default port.
  if (origin && /^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/.test(origin)) return origin;
  return origin && allowed.has(origin) ? origin : null;
}

export function corsHeaders(origin, env) {
  const h = new Headers();
  const ao = allowedOrigin(origin, env);
  if (ao) {
    h.set("Access-Control-Allow-Origin", ao);
    h.set("Vary", "Origin");
  }
  h.set("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
  h.set("Access-Control-Allow-Headers", "Content-Type, X-Friend-Token, Authorization");
  h.set("Access-Control-Max-Age", "86400");
  return h;
}
