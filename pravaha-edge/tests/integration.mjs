// Integration smoke test: boots a mock Render origin + wrangler dev, then
// verifies proxying, caching, auth gating, error handling, and cache isolation.
import { spawn } from "node:child_process";
import { setTimeout as sleep } from "node:timers/promises";

const ROOT = decodeURIComponent(new URL("..", import.meta.url).pathname);
const ORIGIN_PORT = 8799;
const WORKER_PORT = 8787;
const ORIGIN_URL = `http://127.0.0.1:${ORIGIN_PORT}`;
const WORKER_URL = `http://127.0.0.1:${WORKER_PORT}`;
const TOKEN = "test-friend-token";

let originProc, workerProc;
const results = [];
function record(name, pass, detail = "") {
  results.push({ name, pass, detail });
  console.log(`${pass ? "PASS" : "FAIL"}: ${name}${detail ? " -- " + detail : ""}`);
}

async function waitForHttp(url, timeoutMs = 90000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const r = await fetch(url);
      if (r.status < 500) return true;
    } catch {}
    await sleep(500);
  }
  return false;
}

async function killProc(p) {
  if (!p) return;
  try { p.kill("SIGTERM"); } catch {}
  await sleep(500);
  try { p.kill("SIGKILL"); } catch {}
}

async function main() {
  // 1. Start mock origin
  originProc = spawn("/opt/homebrew/bin/node", ["test-origin.mjs"], { cwd: ROOT, stdio: ["ignore", "pipe", "pipe"] });
  let originReady = false;
  originProc.stdout.on("data", (d) => {
    const s = d.toString();
    process.stdout.write("[origin] " + s);
    if (s.includes("MOCK_ORIGIN_READY")) originReady = true;
  });
  originProc.stderr.on("data", (d) => process.stderr.write("[origin-err] " + d));
  const originStart = Date.now();
  while (!originReady && Date.now() - originStart < 15000) await sleep(200);
  if (!originReady) { console.error("Origin did not become ready"); process.exit(1); }

  // 2. Start wrangler dev
  workerProc = spawn("/opt/homebrew/bin/npx", [
    "wrangler", "dev", "--local", "--port", String(WORKER_PORT),
    "--var", `ORIGIN_URL:${ORIGIN_URL}`,
    "--var", `FRONTEND_ORIGIN:http://localhost:${WORKER_PORT}`,
  ], { cwd: ROOT, stdio: ["ignore", "pipe", "pipe"], env: { ...process.env } });
  workerProc.stdout.on("data", (d) => process.stdout.write("[worker] " + d));
  workerProc.stderr.on("data", (d) => process.stderr.write("[worker-err] " + d));

  const ready = await waitForHttp(`${WORKER_URL}/api/health`, 120000);
  if (!ready) {
    console.error("Worker did not become ready");
    await killProc(workerProc); await killProc(originProc);
    process.exit(1);
  }

  // Helper
  async function req(path, opts = {}) {
    const headers = { ...(opts.headers || {}) };
    if (opts.token) headers["X-Friend-Token"] = TOKEN;
    if (opts.origin) headers["Origin"] = opts.origin;
    const r = await fetch(`${WORKER_URL}${path}`, {
      method: opts.method || "GET",
      headers,
      body: opts.body,
    });
    const text = await r.text();
    let json = null;
    try { json = JSON.parse(text); } catch {}
    return { status: r.status, headers: r.headers, text, json, cache: r.headers.get("X-Pravaha-Cache") };
  }

  // 3. Tests
  // T1: cacheable GET without token -> forwarded, not cached (BYPASS)
  {
    const r = await req("/api/bars/TEST");
    record("proxy: GET bars without token forwarded (401 from origin)",
      r.status === 401 && r.cache === "BYPASS", `status=${r.status} cache=${r.cache}`);
  }

  // T2: cacheable GET with token -> MISS then HIT
  {
    const r1 = await req("/api/bars/TEST", { token: true });
    const hitsBefore = (await req("/api/_hits")).json.hits;
    const r2 = await req("/api/bars/TEST", { token: true });
    const hitsAfter = (await req("/api/_hits")).json.hits;
    record("proxy: first token request is MISS", r1.status === 200 && r1.cache === "MISS",
      `status=${r1.status} cache=${r1.cache}`);
    record("proxy: second token request is HIT (origin not re-hit)",
      r2.status === 200 && r2.cache === "HIT" && hitsAfter === hitsBefore,
      `status=${r2.status} cache=${r2.cache} originHits=${hitsBefore}->${hitsAfter}`);
    record("proxy: cached body correct", r2.json && r2.json.symbol === "TEST",
      `body=${r2.text.slice(0, 80)}`);
  }

  // T3: private route -> forwarded, 403, BYPASS (never cached)
  {
    const r = await req("/api/portfolio", { token: true });
    record("auth: private route forwarded 403 BYPASS", r.status === 403 && r.cache === "BYPASS",
      `status=${r.status} cache=${r.cache}`);
  }

  // T4: POST -> forwarded, not cached
  {
    const r = await req("/api/screen", { method: "POST", token: true, body: JSON.stringify({ x: 1 }), headers: { "Content-Type": "application/json" } });
    record("proxy: POST forwarded 200 BYPASS", r.status === 200 && r.cache === "BYPASS",
      `status=${r.status} cache=${r.cache}`);
  }

  // T5: 5xx -> forwarded, BYPASS
  {
    const r = await req("/api/boom", { token: true });
    record("errors: 500 forwarded BYPASS", r.status === 500 && r.cache === "BYPASS",
      `status=${r.status} cache=${r.cache}`);
  }

  // T6: 404 -> forwarded, BYPASS
  {
    const r = await req("/api/nope", { token: true });
    record("errors: 404 forwarded BYPASS", r.status === 404 && r.cache === "BYPASS",
      `status=${r.status} cache=${r.cache}`);
  }

  // T7: CORS preflight
  {
    const r = await fetch(`${WORKER_URL}/api/bars/TEST`, {
      method: "OPTIONS",
      headers: { Origin: "http://localhost:8787", "Access-Control-Request-Method": "GET" },
    });
    record("cors: preflight 204", r.status === 204,
      `status=${r.status}`);
  }

  // T8: CORS allowed origin on cached response
  {
    const r = await req("/api/bars/TEST", { token: true, origin: "http://localhost:8787" });
    record("cors: allowed origin reflected", r.headers.get("access-control-allow-origin") === "http://localhost:8787",
      `acao=${r.headers.get("access-control-allow-origin")}`);
  }

  // T9: disallowed origin -> no ACAO
  {
    const r = await req("/api/bars/TEST", { token: true, origin: "https://evil.example" });
    record("cors: disallowed origin no ACAO", r.headers.get("access-control-allow-origin") === null,
      `acao=${r.headers.get("access-control-allow-origin")}`);
  }

  // T10: cache isolation - a request with a DIFFERENT token context still gets cached body
  // (documented: cached data is token-independent public market data; origin did not echo token)
  {
    const r = await req("/api/bars/TEST", { token: true });
    const leaked = r.text.includes(TOKEN);
    record("isolation: cached body contains no token", !leaked,
      leaked ? "TOKEN LEAKED" : "no token in body");
  }

  // T11: origin down -> 502
  await killProc(originProc); originProc = null;
  await sleep(1000);
  {
    const r = await req("/api/health", { token: true });
    record("errors: origin down -> 502", r.status === 502 && r.cache === "ERROR",
      `status=${r.status} cache=${r.cache}`);
  }

  await killProc(workerProc); workerProc = null;

  const passed = results.filter((r) => r.pass).length;
  const failed = results.filter((r) => !r.pass).length;
  console.log(`\n=== SUMMARY: ${passed} passed, ${failed} failed ===`);
  for (const r of results) if (!r.pass) console.log("  FAIL:", r.name, r.detail);
  process.exit(failed === 0 ? 0 : 1);
}

main().catch(async (e) => {
  console.error("INTEGRATION_ERROR", e);
  await killProc(workerProc); await killProc(originProc);
  process.exit(1);
});
