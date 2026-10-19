# RELEASE READINESS — Mega Tool (NEPSE)

> Evidence-based checklist. Every row is marked from something that was actually
> executed this session (2026-10-16), not from intent. `NOT-TESTED` is used
> where it is honest to say so. **The application was not deployed and was not
> exposed to any network beyond loopback.**

Environment: macOS (darwin), Python 3.12 in `.venv`, single user `ashim`.
Application: local FastAPI + static frontend, DuckDB (market data) + SQLite (app
state). Production instance observed on `127.0.0.1:8710` (PID 26596) — never
touched by this session.

## 1. Local startup

| Item | Status | Evidence |
|---|---|---|
| Runtime requirement documented | TESTED-PASS | `pyproject.toml` `requires-python = ">=3.12,<3.14"` |
| Dependencies installable | TESTED-PASS | `.venv` present; `import megatool.api, megatool.ta` succeeds |
| Dev server starts | TESTED-PASS | `uvicorn megatool.api:app --host 127.0.0.1 --port 8714` served 200 on `/` and 20+ API routes |
| Data directory configurable | TESTED-PASS | `MEGATOOL_DATA_DIR` redirects all storage; used for every QA run |
| Host binding defaults to loopback | TESTED-PASS | `MEGATOOL_HOST` default `127.0.0.1` |
| Startup prints the access-boundary state | TESTED-PASS | new `_log_access_boundary()`; 3 tests |
| Health check | TESTED-PASS | `GET /api/health` → 200 |
| Frontend served by backend | TESTED-PASS | `GET /` → 200, title `Mega Tool — NEPSE Research Terminal` |

> **Phase 2–6 completion status** is tracked separately in
> `docs/PHASES_2_6_COMPLETION_AUDIT.md` (all five phases are **PARTIAL** as of
> 2026-10-16). This file is about *readiness*, not feature completeness.

## 2. Data & storage

| Item | Status | Evidence |
|---|---|---|
| Market DB (DuckDB) initialises | TESTED-PASS | isolated DBs created by fixture + server |
| App DB (SQLite) initialises | TESTED-PASS | `init_app_db()` on startup |
| Single-writer lock is respected | TESTED-PASS | a second connection to a locked DB raised `IOException` rather than corrupting |
| Production DBs not modified | TESTED-PASS | mtimes unchanged (`2026-10-15 09:24:38` / `2026-10-14 15:52:00`) |
| Backup/rollback guidance | TESTED-PASS (documented) | `docs/deployment_architecture.md`; DuckDB = system of record |
| Migration path | NOT-TESTED | no production migration was run (forbidden by safety rules) |

## 3. Data sources

| Source | Status | Notes |
|---|---|---|
| Public GitHub NEPSE daily dataset | TESTED-PASS (read path) | the only populated price source |
| Official NEPSE API | BLOCKED | requires owner authorization; gate `MEGATOOL_NEPSE_API_AUTHORIZED` **unset**, zero requests issued |
| YONEPSE | BLOCKED | supplementary only; data-rights ruling outstanding |
| TMS | BLOCKED | no broker name / URL / read-only basis supplied |
| News | BLOCKED (upstream) | local import/validate/dedup/summary layer works; no machine-readable feed |
| Floorsheet | IMPLEMENTED (data-limited) | import + aggregation tested; no live session data |
| Freshness labelling | TESTED-PASS | `/api/data` renders "stale by N days", "live feed not connected" |

## 4. Security

| Item | Status | Evidence |
|---|---|---|
| Auth boundary deny-by-default when a token is set | TESTED-PASS | `tests/test_friend_access.py` (20 tests: 401/403, allowlist, no token echo) |
| Bound to loopback by default | TESTED-PASS | `HOST` default |
| Non-loopback + no token is warned | TESTED-PASS | new `_log_access_boundary()`; 3 tests; secret never printed |
| CORS restricted | TESTED-PASS | explicit allowlist of loopback + configured origin; methods GET/POST/OPTIONS |
| CORS ≠ auth | TESTED-PASS | documented; the middleware, not CORS, enforces access |
| Input validation | TESTED-PASS | FastAPI constraints → 422; shared `valid_symbol()` on all per-symbol routes |
| No path-traversal surface | TESTED-PASS | no endpoint accepts a filesystem path |
| SQL injection | TESTED-PASS | all queries parameterised via `MarketStore`; no string-built SQL on user input |
| No secret leakage in errors | TESTED-PASS | malformed input → clean 422; no traceback in responses |
| XSS | TESTED-PASS (probes) | journal-thesis and reflect-panel payloads did not execute; static review of 137 `innerHTML` sites found escaping at every leaf; one unescaped date hardened anyway |
| XSS fuzzing | NOT-TESTED | no automated fuzzer was run |
| Dependency vulnerability scan | NOT-TESTED | `pip-audit` is not installed; no scan performed |
| Exposed publicly | NOT-TESTED / N/A | never exposed; nothing published |

## 5. Reliability

| Item | Status | Evidence |
|---|---|---|
| Degenerate input handling | TESTED-PASS | 7 symbols × 12 endpoints: zero 5xx; NaN series → clean 400 on swing endpoints |
| Failure states in the UI | TESTED-PASS | empty states for fundamentals/floorsheet; error banners wired |
| Console errors across all views | TESTED-PASS | **0 errors, 0 warnings** across all 11 views |
| Background jobs | NOT-TESTED | none started this session (no scheduler enabled) |
| Long-run stability | NOT-TESTED | no soak test performed |

## 6. Performance (backend-only, in-process, synthetic — NOT production latency)

Universe 60 symbols × 650 bars, warm, n=12, `TestClient`:

| Endpoint | p50 | p95 |
|---|---|---|
| `/api/dashboard` | 8.1 ms | 8.6 ms |
| `/api/quotes` | 1.3 ms | 1.4 ms |
| `/api/bars/{s}` | 16.6 ms | 17.1 ms |
| `/api/bars/{s}/indicator` | 3.5 ms | 3.7 ms |
| `/api/bars/{s}/patterns` | 4.7 ms | 5.1 ms |
| `/api/bars/{s}/statistics` | 3.3 ms | 4.9 ms |
| `POST /api/screen` | 123.9 ms | 127.7 ms |
| `POST /api/rank` | **113.6 ms** | 115.6 ms |
| `POST /api/backtest` | 8.1 ms | 8.5 ms |
| `/api/stats/correlation` | 5.7 ms | 6.3 ms |

`/api/rank` improved from 391.7 ms → 113.6 ms (3.45×) after vectorising
`rolling_std` (B-50). **These are not live-market or end-to-end numbers.**

## 7. Deployment (preparation only — nothing deployed)

| Item | Status | Notes |
|---|---|---|
| Static-hosting compatibility | TESTED-PASS (documented) | frontend is plain static (no build step) |
| Persistent backend requirement | TESTED-PASS (documented) | DuckDB + SQLite require a persistent host; Netlify alone is insufficient |
| CORS/API base-URL config | TESTED-PASS (documented) | `MEGATOOL_FRIEND_ORIGIN` + `netlify.toml` |
| Env-var documentation | TESTED-PASS | `.env.example`, `docs/deployment_architecture.md` |
| Friend token generation | NOT-TESTED | deliberately not generated (rule: never create a real friend token) |
| Deployment itself | NOT-TESTED | out of scope by instruction |

## 8. Known limitations (unchanged)

Blocked on the owner: official NEPSE authorization, TMS source, YONEPSE
data-rights, friend token + origin. Blocked on upstream data: live news feed.
Not tested: dependency CVE scan, XSS fuzzing, production migration, background
jobs, soak testing, and any real-market latency.

---

## Session 23 (2026-10-16) — deployment-readiness delta

| Item | Status | Evidence |
|---|---|---|
| Dependency vulnerabilities | TESTED-PASS | `uvx pip-audit` → "No known vulnerabilities found" |
| Loopback-only default | TESTED-PASS | `MEGATOOL_HOST` default `127.0.0.1`; dev/QA bound to loopback only |
| Secrets not in the repo | TESTED-PASS | `.gitignore` excludes `.env`, `data/`; live credentials read from env and sent in a POST body, never a URL |
| Live credentials never in the browser | TESTED-PASS | `/api/live/*` returns data only; ShareHub auth is server-side |
| Official surface never auto-enabled | TESTED-PASS | `megatool/live.py` never sets `MEGATOOL_NEPSE_API_AUTHORIZED`; 2 tests assert the gate stays closed |
| Live-data blocker (deployment) | **BLOCKED** | No permitted low-latency source is configured; `/api/live/market` labels the public mirror honestly. A deployment may ship, but must not claim live data. |
| Public-exposure readiness | **NOT-TESTED** | No reverse proxy, TLS termination or auth layer is configured for off-host access; the friend-access boundary exists but has no real token. |

**Deployment blockers (must resolve before a public deploy):**
1. Live data — provide a licensed source (ShareHub) or accept the labelled public
   mirror; never ship the anti-bot official path.
2. Off-host exposure — add TLS termination + the friend-access token, or keep the
   service loopback-only.
3. A product whose live data is blocked or whose security is unverified must not
   be labelled fully production-ready.

---

## Session 24 (2026-10-16) — readiness delta

| Item | Status | Evidence |
|---|---|---|
| Free market data available without auth/key/allow-list | TESTED-PASS | Raw YONEPSE content; 328 quotes, NEPSE 2,625.93, in-session timestamps |
| Data source is honest about freshness | TESTED-PASS | Cadence-aware bands + status vocabulary; measured DELAYED/STALE cases |
| Source provenance is explicit | TESTED-PASS | `origin` reported; Pages fallback flagged in API and UI |
| Fundamentals available | TESTED-PASS | 21,698 records / 307 symbols; ratios unavailable without a price |
| Dependency audit | TESTED-PASS | `uvx pip-audit` clean (session 23; unchanged deps) |
| Official live data | **BLOCKED** | anti-bot token; gate never set |
| ShareHub | **UNAVAILABLE** | paid licence + IP allow-list |
| Off-host exposure | **NOT-TESTED** | still loopback-only; no TLS termination/auth layer |

**Deployment blockers (unchanged):** (1) off-host exposure needs TLS termination,
secure cookies and the friend-access token, or keep it loopback-only; (2) do not
present the labelled public mirror as a real-time exchange feed; (3) background
collector lifecycle for a hosted deployment is not yet built.

---

## Session 25 (2026-10-16) — local release instance

| Item | Status | Evidence |
|---|---|---|
| Dev instance starts | TESTED-PASS | `127.0.0.1:10000` → `/api/health` 200, `/` 200 |
| Isolated dev storage | TESTED-PASS | `MEGATOOL_DATA_DIR=data/dev/release` (own DuckDB + SQLite) |
| Production untouched | TESTED-PASS | PID 26596 alive; prod DB mtimes unchanged; gate unset |
| Real historical data | TESTED-PASS | 372 symbols / 515,327 bars / 1995→2026-10-15 |
| Free market source | TESTED-PASS | YONEPSE raw + commit walk-back; DELAYED, 75.6 min age |
| Fundamentals ratios | TESTED-PASS | NABIL P/E 19.25, P/B 2.21 (reviewed inputs) |
| Charts consume real data | TESTED-PASS | 7 canvases; NABIL · 120 bars · source + "unadjusted" caveat |
| Screener | TESTED-PASS | 372 evaluated, 350 eligible, 18 passed, 22 insufficient |
| Browser console | TESTED-PASS | 0 errors/warnings across all 14 views |
| Dependency audit | TESTED-PASS | `uvx pip-audit` clean |
| **Public/internet deployment** | **BLOCKED** | loopback-only; no TLS termination, no auth layer, no secure cookies, friend token unset |
| Background collector lifecycle | **PARTIAL** | in-process cache only; no scheduler/worker supervisor |
