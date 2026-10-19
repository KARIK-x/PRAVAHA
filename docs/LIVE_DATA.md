# Live NEPSE data — investigation, measured evidence, and what was built

**Session 23 (2026-10-16).** This document answers, with evidence, whether Mega
Tool can show live NEPSE prices, what actually blocks that, and what was
implemented. It is written so the owner can finish the job in one step.

> **Headline.** A live-data subsystem now exists and is wired to the frontend
> (`megatool/live.py`, `GET /api/live/{status,market,quotes}`). It measures
> freshness from the source's own timestamps and never presents stale data as
> live. **Live access itself remains BLOCKED**: the only near-real-time free
> source (the official NEPSE API) requires defeating the exchange's anti-bot
> token, which this project will not do; the legitimate low-latency source
> (ShareHub, ~20 s) needs the owner's licensed credentials. The always-available
> public mirror is currently ~4 days stale.

## 1. The exact blocker, measured

Probes were bounded and made once each; TLS verification stayed on.

| Probe | Result | Meaning |
|---|---|---|
| `GET /api/nots/market-open`, `market-summary`, `nepse-index`, `security` (no token) | **HTTP 401**, body `WARNING: UNAUTHORIZED ACCESS` | The official data endpoints refuse any request without a `Salter` token. |
| `GET /api/authenticate/prove` (browser User-Agent) | **HTTP 200** — `salt1..salt5`, a 250-char JWE `accessToken` | The token is a *challenge*; producing the accepted token means running NEPSE's embedded WASM to decide which characters to strip. |
| Same endpoint with `curl` UA | HTTP/2 `PROTOCOL_ERROR` | NEPSE also filters on the browser fingerprint. |
| TLS handshake, `nepalstock.com.np:443` | **verify OK** — DigiCert/GeoTrust, valid 2025-12-12 → 2026-12-10, SAN covers `nepalstock.com.np` | TLS is *not* the blocker; verification works and stays on. |

**So the blocker is not the network, not the certificate, and not the gate
alone.** It is that the official API's accepted token can only be produced by
defeating a client-side anti-bot control. Two rules apply at once:

1. *Never bypass anti-bot controls* — a hard rule, independent of any owner wish.
2. *Keep the official surface behind `MEGATOOL_NEPSE_API_AUTHORIZED`* — the owner
   gate, which is unset.

The gate is therefore **not** the only thing standing in the way, and opening it
would not be sufficient — nor would it be permitted while the anti-bot bypass is
required. This is why live data is reported **BLOCKED**, and why the go-nepse
bridge (which *does* perform the bypass internally) stays inert.

## 2. Provider comparison (verified facts vs claims)

| Provider | Access requirement | Cadence | Cost | Reachable now? | Verdict |
|---|---|---|---|---|---|
| **NEPSE official** `/api/nots` | Salter token = anti-bot bypass | near-real-time when open | — | 401 without token | **Not permitted** by project rules |
| **ShareHub NEPSE Data API** | Licensed account (email+password) **and** server-IP allow-list | **~20 s** live; 5 min closed (documented) | licence; price on request (not published) | reachable (`/my-ip` 200 in 0.14 s) | **Best legitimate option**; needs owner credentials |
| **YONEPSE** (public GitHub mirror) | none | hourly (documented) | free (public) | reachable, but market files **stale since 2026-10-12** | Implemented as the fallback; honestly labelled |
| **NEPSEAPI** (`nepseapi.com`) | early access by email | "real-time" (claim, unverified) | unknown | no public endpoint | **Not available** |
| **NepseAPI-Unofficial** (hosted, free) | none (rate-limited 60/min) | documented `max-age=30` | free, educational-only, no uptime guarantee | **HTTP 522 (down)** in 19.7 s | Unreliable; not integrated |
| **Owner feed URL** | whatever the owner is authorized to use | owner-defined | owner-defined | n/a | Implemented (`MEGATOOL_LIVE_FEED_URL`) |

**Cost note.** No per-second source publishes a price. ShareHub's documentation
enumerates packages but not prices; NEPSEAPI is early-access only. So "verified
cost" is: **not publicly documented for any candidate.**

## 3. Measured latency vs observation freshness

The point of §2.4 of the mission, demonstrated live:

| Measurement | Value | Reading |
|---|---|---|
| `GET /api/live/market` request latency (YONEPSE) | **1,334 ms** | the request was slowish |
| Newest observation in that payload | **2026-10-12T09:14:59Z** | …but the data is **338,978 s (≈3.9 days)** old |
| Resulting label | **`stale`** | not "live" |

A fast request returning an old snapshot is reported as an old snapshot. The
decomposition the mission asked for is present in the API:

- **source publication latency** → `observed_at` (the publisher's own stamp)
- **collection latency** → `fetch_latency_ms`
- **cache age** → `cache_age_seconds`
- **end-to-end observation age** → `age_seconds` (what the UI shows)

## 4. What was built

### Backend — `megatool/live.py`
A provider-agnostic live layer with four providers and honest freshness:

| Provider id | Source | Enabled when |
|---|---|---|
| `sharehub` | ShareHub licensed API (~20 s) | `MEGATOOL_SHAREHUB_EMAIL` + `MEGATOOL_SHAREHUB_PASSWORD` set |
| `official` | go-nepse bridge (near-real-time) | gate open **and** bridge built (**not enabled**) |
| `feed` | any owner-permitted JSON URL | `MEGATOOL_LIVE_FEED_URL` set |
| `yonepse` | public mirror (hourly) | always (fallback) |

Behaviour that matters:
- **Freshness is measured, never asserted.** `age_seconds` comes from the
  source's own newest timestamp; `freshness` ∈ {`live`, `recent`, `delayed`,
  `stale`, `last-close`, `unknown`}.
- **No invention.** A missing/invalid price is `null` with a
  `validation_status`, never a `0`; `high < low` is marked `suspect`.
- **No request storms.** Each provider has a publication cadence; the service
  caches at that cadence, so the UI cannot poll a 20 s source every second.
- **Failure is explicit.** An unconfigured/unreachable/malformed provider yields
  a reason, never a fabricated snapshot.
- **TLS stays verified**; credentials travel in a POST body, never a URL.
- **The module never sets the gate.**

### API — read-only
| Route | Purpose |
|---|---|
| `GET /api/live/status` | which providers exist and why each is (un)available — network-free |
| `GET /api/live/market` | freshest market snapshot + measured freshness |
| `GET /api/live/quotes?symbols=…` | per-symbol quotes + freshness |
| `GET /api/status` | now reports `live_feed_connected` and the provider block honestly |

### Frontend
A **Live market** strip on the Overview: provider, a freshness badge
(`live`/`recent`/`delayed`/`stale`), market open/closed, NEPSE index + change,
**observed age**, quote count, the source's own timestamp, a *Refresh now*
button, and the note that age is end-to-end, not request speed. It polls only
while Overview is visible and stops when you leave.

## 5. Does data reach the frontend?

**Yes** — verified in the browser. With only the public mirror available the
strip renders *stale · 3.9 d · 368 quotes · NEPSE 2,591.81*. When the owner
configures ShareHub or the gate, the same strip renders the live figure with a
`live` badge and sub-minute age, with no code change.

## 6. The exact next step to get live data (owner action)

**Option A — ShareHub (recommended; ~20 s, legitimate):**
1. Obtain a ShareHub Data API licence for the endpoint services you need.
2. From this server, call `GET https://sharehubnepal.com/data/api/v1/nepse-data/my-ip`
   and give ShareHub the returned IP for the allow-list.
3. Run the app with `MEGATOOL_SHAREHUB_EMAIL` and `MEGATOOL_SHAREHUB_PASSWORD`
   set **in the server environment** (never in the browser or the repo).
4. Open Overview; the badge should read `live`/`recent`.

**Option B — your own permitted feed:** set `MEGATOOL_LIVE_FEED_URL` to a JSON
feed you are authorized to use (your broker's read-only TMS endpoint, a licensed
vendor, or your own collector). The schema is a list of quote objects or an
object with a `quotes` array; `last_updated`/`as_of` timestamps drive freshness.

**Option C — the official API:** requires accepting the anti-bot library *and*
setting `MEGATOOL_NEPSE_API_AUTHORIZED=1`. **This project will not enable it**
because it means defeating a control the exchange put in place. If the owner
obtains a *sanctioned* official access route, wire it as a `feed` URL.

## 7. Why not "just build a scraper from scratch"

Building our own client would still have to produce the Salter token, i.e.
reproduce the same WASM bypass the library uses — the anti-bot problem is in the
data source, not the client. A scraper of a *third party's* site would be
unauthorized access to a source we have no agreement with. Neither is permitted.
The honest paths are a **licensed feed** (ShareHub), the **owner's own** feed, or
the public mirror with its real age on the label.

## 8. Remaining limitations

- No free, public, sub-second NEPSE feed was found. Verified: official = anti-bot;
  public mirrors = hourly and currently stalled; unofficial hosted = down (522).
- The YONEPSE fallback can be days stale; it is labelled, never hidden.
- ShareHub's live JSON shape is implemented from its published field names and
  covered by fixture tests; it has **not** been exercised against a real licence
  (none available here), so its live path is **NOT-TESTED** until the owner runs it.
- The `official` provider is implemented but deliberately inert.
- Market-closed observations are labelled `last-close`, not `stale`, because an
  hours-old last close is expected — but the age is still shown.

---

## Diagnostic pass (2026-10-16, follow-up) — *does go-nepse actually work?*

**Question:** can the existing `github.com/voidarchive/go-nepse` integration
retrieve genuine, sufficiently fresh NEPSE data — i.e. is ShareHub even needed?

**Answer: cannot be established, and it does not matter for our decision — the
library is unusable by policy.** Detail below.

### What was inspected (no network)

| Item | Finding |
|---|---|
| Library version | Module **v0.2.5** (latest on `proxy.golang.org`; no newer tag). `nepse.Version` const still says `0.2.0`. `CHANGELOG` last release **0.2.0 (2026-01-03)**; "unit tests / integration tests / rate limiting" still *Planned*. **Effectively unmaintained.** |
| Auth mechanism | `internal/auth/parser.go` + `css.wasm`: `WASM(salt1..5) → 5 strip indices → remove those chars from `accessToken` → `Authorization: Salter <token>``. The file comment says the WASM "replicates the browser's decoding logic". This **is** an anti-automation circumvention. |
| Token refresh | `Manager` refreshes at 45 s (`singleflight`, one refresh per herd); `ForceUpdate` on 401. |
| Bridge methods | `market-summary`, `market-status`, `securities`, `find-security`, `live-market` (`/api/nots/lives-market`), `price-history`, `nepse-index`, `sub-indices`, `company`, `company-profile`, `dividends`, `floorsheet`, `market-depth`. |
| Gate | The bridge refuses the real host unless `MEGATOOL_NEPSE_API_AUTHORIZED=1` (exit 3). The Python `OfficialProvider` refuses earlier for the same reason. Neither ever sets the flag. |
| TLS | `Options.TLSVerification=true`; explicitly re-checked this pass — cert verifies (`ssl_verify_result=0`). TLS is **not** the blocker. |
| Supply-chain note | The module ships a **12 MB x86-64 Linux ELF named `basic`** in its root, referenced by **no** `.go` file. Go does not compile it, so it never runs, but a stray prebuilt binary in a dependency is a hygiene/red flag. |

### Live probes attempted (bounded, no bypass, one each)

Local receipt time **2026-10-16T07:42:36Z** (13:27 NPT).

| Endpoint | HTTP | Duration | Body | Records | Provider timestamp | Age |
|---|---|---|---|---|---|---|
| `/api/nots/nepse-data/market-open` | **401** | 0.046 s | `WARNING: UNAUTHORIZED ACCESS` | 0 | none | n/a |
| `/api/nots/market-summary` | **401** | 0.031 s | same | 0 | none | n/a |
| `/api/nots/nepse-index` | **401** | 0.032 s | same | 0 | none | n/a |
| `/api/nots/lives-market` | **401** | 0.031 s | same | 0 | none | n/a |
| `/api/authenticate/prove` (browser UA) | 200 | — | `salt1..salt5`, 250-char JWE `accessToken`, `refreshToken`, `serverTime` | 1 challenge | `serverTime` | n/a |

**HTTP success ≠ current data:** the only 200 is a *challenge*, not a quote.

### Why no live smoke test was run

go-nepse can only obtain an accepted token by performing the WASM strip. Running
the library against the official host therefore *requires* the anti-bot
circumvention, which the diagnostic brief prohibits ("Do not perform this test if
it would require bypassing authentication, anti-bot protections…"). The test was
**not performed**. The verdict is therefore about policy, not about a proven
technical failure.

### Compatibility observation (does not require the bypass)

The live challenge still contains **all eight** fields `TokenResponse` decodes
(`salt1..salt5`, `accessToken`, `refreshToken`, `serverTime`); extra keys
(`salt`, `tokenType`, `isDisplayActive`, `popupDocFor`) are ignored by Go's
decoder. So the library's *input parsing* is still compatible. Whether the
**stripped token is accepted** is unverifiable without sending it — i.e. without
the prohibited bypass.

### Classification

**BLOCKED_BY_ACCESS_RESTRICTIONS** (live path also **NOT_TESTED**).

- Not `BLOCKED_BY_AUTHENTICATION`: no credential is missing.
- Not `BLOCKED_BY_NETWORK_OR_ENVIRONMENT`: endpoints answer in ~30 ms; TLS verifies.
- Not `WORKING`/`WORKING_BUT_STALE`: nothing was retrieved.
- The block is the exchange's anti-bot token scheme, which the library exists to
  defeat and which we will not defeat.

### Does this mean ShareHub is necessary?

For live data **under this project's rules, yes** — go-nepse is unusable by
policy, so a licensed/owner feed is the only compliant route. Two caveats:

1. This is a **policy** conclusion, not proof that go-nepse is broken. Whether it
   *technically* works is UNKNOWN and untestable here.
2. ShareHub is **not proven** to solve it either; its live path is fixture-tested
   only. Validate it first in **ShareHub test mode** (`X-DataApi-Test: true`, up
   to 10 req/min before an IP allow-list is added) **before paying**, then decide.

---

## Session 24 — the free source works; the staleness was a CDN, not the data

### The root cause of the "3.9 days stale" finding

The YONEPSE adapter read `https://shubhamnpk.github.io/yonepse` — the
**GitHub-Pages mirror**, which is CDN-cached. The repository's **raw content**
(`raw.githubusercontent.com/.../main`, updated by the scraper's commits) was, at
the same moment, **current**. Measured 2026-10-16:

| Source | `status.json` `last_checked` | NEPSE index `generatedTime` | Verdict |
|---|---|---|---|
| GitHub Pages mirror | `2026-10-12T10:17:11` | `2026-10-12T15:16:00` | ~4 days stale (cached) |
| **Raw content** | **`2026-10-16T07:17:03`** (31 min old) | **`2026-10-16T13:01:00`** (32 min old) | **current** |

Raw `market/live.json` returned **328 quotes**, `is_open: true`, with per-symbol
`last_updated` values inside the live session (e.g. `12:56`, `13:01` NPT). So the
free public source is genuinely usable — the bug was pointing at the wrong mirror.

### What changed

* `megatool/datasources/yonepse.py`: `BASE_URLS = (RAW, PAGES)` — **raw first**,
  Pages only as a fallback; new `fetch_market_indices()` and
  `fetch_market_snapshot()` (which reports **which mirror answered**).
* `megatool/live.py`: **cadence-aware freshness** and the diagnostics **status
  vocabulary**. Providers now declare a `publish_cadence_seconds` (YONEPSE 3600,
  ShareHub 20, official 5, feed 15) separate from the poll `cadence_seconds`.

### Freshness, corrected

An hourly publisher is not "stale" merely for being 40 minutes old, and a
20-second publisher is not "live" at 30 minutes. So:

| Label | Criterion (market open) | Status shown |
|---|---|---|
| `live` | age ≤ 30 s | LIVE_VERIFIED |
| `delayed` | age ≤ max(1.5 × publish cadence, 90 s) | DELAYED |
| `stale` | beyond that | STALE |
| `last-close` | market closed, ≤ 3 days | DELAYED |
| `historical` | > 5 days | HISTORICAL |
| `unknown` | no provider timestamp | UNKNOWN |

Observed with the raw source during the session: **age ≈ 37–43 min → `delayed`**.
`LIVE_VERIFIED` is never shown for a mere HTTP 200.

### A real upstream incident, handled honestly

During this session the repository briefly served a **git merge-conflict** commit:
the raw `status.json` contained `<<<<<<< HEAD` markers and was not valid JSON. The
adapter fell back to the Pages mirror, and — because the snapshot carries the
mirror it used — the API and UI reported `STALE` (age 4.0 d) **with the origin
shown** and an explicit note that the raw content was unreadable. No conflict
markers are ever "repaired" into data, and nothing stale is presented as live.

### Real fundamentals, free

`data/company/financials.json` from the same raw source yields **21,698 records
across 307 symbols** (EPS, P/E, net-worth-per-share, paid-up capital, profit),
imported via the existing `fundamentals` pipeline. Example: NABIL EPS 28.36
(reported). The ratios endpoint correctly returns **P/E / P/B / dividend-yield =
unavailable** when no stored close exists — *"a price must not be invented"* —
rather than fabricating one.

### Still blocked, unchanged

* **Official NEPSE API**: `401 WARNING: UNAUTHORIZED ACCESS`; the accepted token
  requires the anti-bot WASM strip (not performed). The `official` provider stays
  inert and the gate is never set by the app.
* **go-nepse**: same anti-bot dependency; not exercised live.
* **ShareHub**: reachable but needs a licence + IP allow-list → UNAVAILABLE, not
  purchased.

### Free-source comparison (verified this session)

| Source | Free? | Auth/key? | IP allow-list? | Cadence | Verdict |
|---|---|---|---|---|---|
| YONEPSE raw content | **yes** | none | no | ~hourly in-session | **USED** — current-day |
| YONEPSE Pages mirror | yes | none | no | CDN-cached | fallback only (can be days stale) |
| Official NEPSE `/api/nots` | — | anti-bot token | no | near-real-time | BLOCKED (policy) |
| ShareHub Data API | no (licence) | email+password | **yes** | ~20 s | unavailable (paid) |
| Owner feed URL | owner | owner | owner | owner | supported, unset |

---

## Session 25 — resilient free data, and a real historical universe

### The upstream merge-conflict incident, handled

YONEPSE's automations landed a **merge-conflict commit** on its only branch: every
market file contained `<<<<<<< HEAD` markers instead of JSON. Rolling back was not
possible (the branch tip *is* the broken merge), and the GitHub-Pages mirror was
days stale. The adapter now:

1. reads `main`;
2. if unreadable, walks back through recent commits (GitHub API, cached 10 min)
   and uses the **newest parseable** quote board — not merely the first that
   parses, because an older commit can parse while carrying older prices;
3. only then falls back to the Pages mirror, and reports **which ref answered**
   (`origin`) plus a note explaining why.

Measured during the incident: the app served **today's** data (NEPSE 2,625.93,
328 quotes) from commit `f8941a30` rather than the 4-day-old mirror. Conflict
markers are never repaired into data — a broken payload fails and the next ref is
tried.

### A real historical universe (free)

`megatool fetch` (source `github.com/Aabishkar2/nepse-data`, community-maintained,
git-ignored, per-row attribution):

| Metric | Value |
|---|---|
| Symbols | **372 / 372 succeeded** |
| Rows | **515,327** (482,546 new; 32,781 refreshed) |
| Coverage | **1995-07-20 → 2026-10-15** |
| Flagged | 13,258 (recorded, never deleted or repaired) |

### Fundamentals ratios now compute

Ratios refuse `extracted` (unreviewed) values by design. A new explicit,
source-scoped operator action closes that loop:

```
python -m megatool.cli fundamentals review --source yonepse/financials.json
# promoted: 21698
```

With prices present, ratios derive from real inputs and show the verification
level, e.g. **NABIL P/E 19.25** (EPS 28.36, 2026-08-06, `reviewed`,
`yonepse/financials.json`) and **P/B 2.21**. Dividend yield stays `null` — no DPS
records exist, and none are invented.

## Go NEPSE library — diagnostic verdict (follow-up pass)

* **Library:** `github.com/voidarchive/go-nepse`, module tag **v0.2.5** (latest on
  proxy.golang.org; project pins v0.2.5 via `go.mod`); library const reports
  `Version = 0.2.0`. Last upstream release 0.2.0 (2026-01-03); "unit tests,
  integration tests, rate limiting improvements" still in the plan. Effectively
  unmaintained.
* **Bridge methods:** `market-summary`, `market-status`, `securities`,
  `find-security`, `live-market` (`/api/nots/lives-market`), `price-history`,
  `nepse-index`, `sub-indices`, `company`, `company-profile`, `dividends`,
  `floorsheet`, `market-depth`.
* **Auth mechanism:** `internal/auth`: WASM (`embedded css.wasm`) extracts 5
  salt values → computes 5 character positions per token via the wasm functions
  → strips those characters from both `accessToken` and `refreshToken` →
  `Authorization: Salter <token>`. This **replicates NEPSE's client-side
  obfuscation** — i.e. an anti-bot/anti-automaton control. `[roles/transport.go]`
  uses `InsecureSkipVerify = !options.TLSVerification`.
* **Probe results (bounded, one each):** every `/api/nots/*` endpoint tried
  → **HTTP 401 `WARNING: UNAUTHORIZED ACCESS`** in ~0.031 s; `/api/authenticate/prove`
  → HTTP 200 returning a **challenge** (`keys: serverTime, salt, salt1..salt5,
  accessToken (len 250), refreshToken, tokenType`). TLS cert verify = OK (the
  host is reachable; the blocker is not the network or TLS).
* **Challenge shape:** still matches `auth.TokenResponse{salt1..5, accessToken,
  refreshToken, ServerTime}` — so the library's input parsing is compatible, BUT
  whether the derived `Salter` token would be accepted is unverifiable without
  sending it (the prohibited bypass). Conclusion: implementation-compatible but
  acceptance unverified.
* **Why blocked (rule-level, not just config-level):** the library's *only* access
  path is the anti-bot WASM token strip. Setting
  `MEGATOOL_NEPSE_API_AUTHORIZED=1` would enable the code path, not bypass the
  anti-bot. The project rules forbid both: do not bypass anti-bot controls, and
  do not set the gate. Hence live access is BLOCKED whether or not the API
  technically works.
* **Supply-chain note:** the module ships a 12 MB ELF x86-64 *Linux* binary
  `basic` in its root, unreferenced by any `.go` file. Go does not compile it,
  so it never runs, but it does not belong there. Flag before wider adoption.
* **App-side wiring:** `OfficialProvider` (live layer) calls
  `GoNepseAdapter.live_market() / market_status() / nepse_index()` — gated,
  behind the `official` provider. Not in price ingestion or charts (these use the
  stored DuckDB bars). Verified via `/api/gonepse/status` (gate closed →
  `live_connection_tested: false`, `blocker: "anti-bot token obfuscation + owner
  gate"`). `GoNepseAdapter` (21 Python tests) is fixture-tested only.
* **Recommendation:** do not use go-nepse for live data. **Use YONEPSE raw content
  (live layer, `~1h`, now wired and labelled DELAYED)** for a free honest feed,
  or a ShareHub licence for ~20 s (validate in ShareHub test mode first, 10/min,
  500/day, any IP). Do NOT run go-nepse against NEPSE's API to "check whether
  it works" — that *is* the prohibited act.

## Free Nepali aggregator sites — evaluation (five candidates)

These were explicitly inspected because the user asked whether any could supply
near-real-time NEPSE data for free. **None could be verified as permitted,
documented, or meaningfully faster than the YONEPSE raw mirror (~1 h).**

| Candidate | Auth key? | Documented API? | ToS on automation | robots.txt / access | Freshness observed | Verdict |
|---|---|---|---|---|---|---|
| **hamroshare.com.np** | unclear (site + API keys) | none public; /api/ explicitly `Disallow`ed | **"Scrape, mirror, or commercially redistribute our data without written permission"** + bot detection → bans | `/api/` disallowed; AI bots mostly allowed on marketing pages | live-market is an SPA; public HTML contains no market table (the table hydrates from the disallowed API) | **NOT PERMITTED** (explicitly forbidden by ToS + robots) |
| **merolagani.com** | n/a | none documented | site deploys ASP.NET WebForms + VIEWSTATE/stateful; no API grant | `/robots.txt` returns 404 | public `LatestMarket.aspx` renders NABIL→547.00 etc. as HTML; **no timestamp** or "last updated" surfaced | scraping would depend on undocumented HTML; stale/partial; not permitted (unknown ToS) |
| **nepsealpha.com** | likely (and paywall) | none public | not stated clearly | **Cloudflare challenge** (`Just a moment…`) for a browser UA; blocks non-human requests | cannot determine (HTTP 403) | **BLOCKED** — anti-bot (enforced Cloudflare); scraping would violate project rule |
| **chukul.com** | likely | 200 on `/api`, `/docs`, `/login` but returns an **SPA shell** (~1,860 bytes) with no market data | robots allows ``User-agent: *`` but blocks **all major AI/answer-engine crawlers entirely** (`Disallow: /`) | terms pages return SPA shell; market data is JS-hydrated from an API; not a public API | could not read without reverse-engineering the (disallowed-for-AI) client API | **BLOCKED / undocumented** — no evidence of a permitted public data API |
| **nepsetrading.com** | unknown | none public | generic (`restrict or inhibit anyone else's use`; bot scans in robots) | robots blocks only charting_library/paths; broad allow but no license | 590 KB HTML with timestamps (13:08–13:25) but **no extractable price rows**; appears to be a Next.js shell whose market table hydrates client-side | NOT PERMISSIBLE TO VERIFY — no documented API; rendering is client-side and parsing it would be scraping |

### Common findings

- None of these expose a **documented, permitted, structured** market-data endpoint; all are HTML application shells that fetch data through private/internal endpoints.
- Their `robots.txt` disallows their data surfaces (Hamroshare `/api/`, NepseAlpha `/api/*` and `/rest/v1/*`); the others only block AI crawlers.
- Even "permitted" reads of the public page do not give usable freshness — hamroshare's page contains 152 (likely per-row trade times) but no single "snapshot updated at" timestamp, and no easy repeatable scrape.
- These are aggregators that themselves depend on NEPSE/scrape — a chain with the same ToS posture as `nlethetech`.

### Conclusion

None of the five satisfies "legitimate, documented, faster-than-~1 h" access. The fastest *permitted* free source available remains YONEPSE raw content (wired, **DELAYED ~30–76 min, labelled**). ShareHub test-mode (~20 s, **X-DataApi-Test: true**, any IP pre-registration, 10/min, 500/day) remains the cheapest *testable-before-paying* path; it requires the user's ShareHub Data API account credentials (off-limits to share here — set as env vars).

**Recommendation: do not build a scraper against these five sites.** Continue using the YONEPSE live layer honestly labelled as DELAYED, with the free commit-walkback fending off upstream breakage, and limit expectations to ~1 h cadence. If sub-minute is mandatory, the next legitimate step is ShareHub test mode (free) to verify fit before licensing — not scraping these sites.

## Smallest safe next step (user)

1. Leave YONEPSE raw as the active live provider (it is the fastest free one).
2. Set `MEGATOOL_SHAREHUB_EMAIL`+`MEGATOOL_SHAREHUB_PASSWORD` in the *server*
   environment (never the browser or repo) and use ShareHub **test mode**
   (`X-DataApi-Test: true`) to confirm whether ~20 s data satisfies you before
   licensing. Do not use test mode for production.
3. If you want to keep using `go-nepse`, explicitly sign off on the anti-bot
   bypass (the safety rule this project follows forbids it otherwise).
4. Do not add scrapers against hamroshare/merolagani/nepsealpha/chukul/nepsetrading
   — three are explicitly ToS-restricted or anti-bot-gated and none is <1 h.

## Expanded NEPSE data-source candidates (deepened)

Additional candidates explicitly inspected during the "no paid subscriptions" pass.
None of them is **both** permitted (per their own terms / robots) **and** faster
than the ~1 h YONEPSE raw mirror that is already wired. Verifications were
read-only single GETs; no anti-bot bypass, no paid credential, no credential
exposure.

| Candidate | Type | Auth / access | Cadence evidence | Permitted for automated reuse? | Verdict |
|---|---|---|---|---|---|
| `github.com/Shubhamnpk/yonepse` | public mirror (GitHub Pages / raw) | none | ~1h in-session, sometimes stalled | **yes** (public assets; site published raw mirror; MIT-licensed scraper, data is a republish) | **USED** — primary live path |
| `github.com/Aabishkar2/nepse-data` | daily CSV (GitHub) | none | daily; 515k rows, 372 symbols, 1995→2026-10-15 | yes (per-row attribution, already ingested) | **USED** — historical backstop |
| `github.com/nlethetech/nepse-quant-terminal` | Textual TUI; scrape-based historical DB (~13 MB) | none (self-host) | daily incremental; "live quotes" via scrape of third parties | unclear (their data likely scraped) | **DECLINED** — scrape lineage; OLAP subset duplicate of binayabaral |
| `github.com/menaceXnadin/nepsepy` | Python lib; "performs the same login-free bootstrap used by NEPSE's frontend" — i.e. **the same WASM anti-bot bypass** + rate-limit surfaced | none | whatever the underlying off-screen NEPSE API returns (obfuscated-token dependent) | same legal posture as go-nepse | **BLOCKED** — validates go-nepse path choice; same anti-bot |
| `github.com/dipalkatuwal/nepseman-api` | self-hosted / hosted FastAPI + WS; "auth implemented from scratch using NEPSE's own `.wasm` binary" | none externally (self-host) | documented WebSocket `prices/live`, hosted `https://nepseman-api-production.up.railway.app` (may terminate) | self-host reverse-engineering; educational only; "data accuracy is not guaranteed" | **NOT RELIABLE/PERMITTED for production** — ToS it breaks is the exchange's, not ours to take; hosted uptime unguaranteed |
| `github.com/surajrimal07/NepseAPI-Unofficial` | self-host FastAPI + WebSocket; explicitly "for educational and non-commercial use" | none local; hosted at nepseapi.surajrimal.dev | unknown; rule "non-commercial" | **not permitted for commercial/production** | **DECLINED** for our use, and the hosted instance returned **522** during our probe |
| `ra8in/nepse_data_api`, `rajeevpaudel/nepse-api`, `dipalkatuwal/nepseman-api`, `gsubigya/nepseAPI` | Python wrappers | typically official/anti-bot bootstraps | vary | likely the same bypass | cand can be ignored — these do not evade the underlying anti-bot |
| `OmitNomis/ShareSansarScraper`, `SamirWagle/Nepse-All-Scraper` | GitHub-Actions scrapers | scrape; ToS risk | daily-ish | uncertain | **not adopted** (scraper posture, last resort) |
| **hamroshare.com.np** | public site | **ToS explicit**: "Scrape, mirror, or commercially redistribute our data without written permission" + bot-detection bans | page-only, no timestamp header | **not permitted** | robots explicitly `Disallow: /api/` — Respect, do not use |
| **merolagani.com** | public HTML, ASP.NET `__VIEWSTATE` | n/a | no timestamp surfaced in HTML; "LastMarket.aspx" carries LTP-like cells (NABIL 547.00 was visible) | no documented API | appears as wrap-around of NEPSE/ShareSansar; no timestamp on the page | Not better than YONEPSE |
| **nepsealpha.com** | login/JWT (their own fair) | **Cloudflare challenge** at request time from our environment | 403 during probe | neutral/caught-behind-anti-bot | unknown | **blocked from automation** (anti-bot = cannot use) |
| **chukul.com** | SPA shell (1.8 KB); data hydrates from an undocumented client API | terms only surface via robots: blocks all major AI/answer bots (`Disallow: /`) | unknown | no timestamps | short | **insufficient evidence**; robots restrictive for our user agent → avoid |
| **nepsetrading.com** | large CRA/Next shell (590 KB) | not clearly documented | unverifiable; timestamps present but ambiguous | uncertain | not a recognized public data contract | Avoid |
| **pro.sharesansar.com / apps/...** | appears private/app | account-protected | n/a | n/a | n/a | Do not use |
| **NEPSE.gov.np / www.nepalstock.com.np** | official site (anti-bot / WAF at /; 403 if not browser) | effective geo/anti-bot | n/a | n/a | no public API | Use only the permitted public document contexts already in the repo |

### Smallest actionable free path, in priority order

1. **Keep YONEPSE raw content** — it is the fastest *legitimately available*
   end-to-end feed: published permission-free as a public GitHub data asset, ~1 h
   cadence, refreshes during market hours, labelled DELAYED + measured age.
   Stop treating the stale Pages CDN mirror as a data source (we kept it only as a
   transparent fallback).
2. **ShareHub test mode** (`X-DataApi-Test: true`, 10/min, 500/day, any IP pre-registration)
   if sub-hourly is truly needed — validate the `market/` + `stock-prices/` payloads
   against real days before any licence purchase. Credentials must come from the owner,
   not the repo.
3. **Do not** adopt `menaceXnadin/nepsepy` to "save effort": despite being a Python
   package, it performs the *same* WASM anti-bot bypass. It would re-legalize an access
   method the project has deliberately rejected. Same conclusion for
   dipalkatuwal/nepseman-api and NepseAPI-Unofficial (whether self-hosted: it is still
   reverse-engineered from NEPSE's anti-bot path).
4. **Do not scrape any of the 5 sites listed above** — Hamroshare and NEPSEAlpha
   specifically forbid and/or interrupt automation; the rest cannot be verified as
   permitted. The daily *verified* local dataset (binayabaral/Aabishkar2, 515 k bars,
   372 symbols, provenance retained) plus the YONEPSE hourly board is the honest
   best free stack.

### Next free-supplementary-data (legal, reproducible) option

- Ingest `Aabishkar2/nepse-data` (already supported via `megatool fetch`) as the
  long-horizon daily backstop (already 515 k rows ingested into dev: 1995→2026-10-15).
- Import `YONEPSE/data/company/financials.json` for fundamentals (EPS/P/E/net-worth
  per share): **21,698 rows across 307 symbols**, ingested (records are `extracted`,
  not "verified"; ratios therefore stay unavailable through the existing safe path).
- Treat anything faster than ~1 h as either a licensed feed (ShareHub) or an
  owner-authorized waiver that explicitly overrides the anti-bot policy.

## Candidate review — expanded fifth-pass

**Merolagani (`merolagani.com/LatestMarket.aspx`)**

- HTTP 200, ASP.NET WebForms HTML (~26 KB).
- Its own `Disclaimer.aspx` states (verbatim, retrieved 2026-10-16):
  > "As such, users are strictly prohibited from employing any automated data
  > collection methods, including but not limited to scripts, APIs, screen
  > scraping, data mining, robots, or other data gathering and extraction tools,
  > regardless of their intended purposes. The use of any technology to
  > circumvent..."
- And: "only for your own personal use", "Nepal copyright law and international
  treaties", no third-party commercial redistribution without prior written
  permission.
- The market page itself prints symbol-ltp-change-open-high-low-volume rows
  (e.g. NABIL 547.00 ...) **without a source timestamp**, so freshness cannot
  even be assessed, let alone claimed.

**Conclusion for Merolagani:** NOT PERMITTED for automated collection. Explicitly
prohibited by its own published legal terms (more restrictive than HamroShare's
robots). This closes the question of "can we just scrape Merolagani to get
live-ish data" — **no**.

Updated candidate table:

| Candidate | Permitted for automation (evidence) | Fresher than YONEPSE raw (~1 h)? | Verdict |
|---|---|---|---|
| MEROLAGANI | **NO** (Disclaimer explicitly bans scripts/APIs/scraping/robots, personal use only) | n/a — not permitted | **Do NOT scrape** |
| HAMROSHARE | **NO** (Terms: "Scrape, mirror, or commercially redistribute our data without written permission"; `/api/` Disallowed) | unknown (page has no global "as of") | **Do NOT scrape** |
| NEPSEALPHA | **NO (de facto)** — Cloudflare challenge blocks non-human clients | unknown | **Blocked** by anti-bot gate (cannot verify) |
| CHUKUL | inconclusive (SPA only) | unknown | avoid (robots blocks AI bots; non-documented internal API) |
| NEPSETRADING | unclear terms | unknown | avoid — no documented endpoint |
| YONEPSE raw (USED) | **YES** (public raw content) | ~30–76 min | best free; final verdict: keep |
| go‑NEPSE / nepsepy / nepseman | reverse-engineered WASM | near-real-time theoretical | **POLICY-BLOCKED** (anti-bot bypass) |
| NEPSEAPI-Unofficial | "educational/non-commercial only" | claims real-time, unverified | hosted UNRELIABLE (HTTP 522) + ToS unclear |
| ShareHub (paid/test) | licensed + IP allowlist | ~20 s (documented, untested by us) | cheapest **sub-hourly** viable path |

**No site that's faster than YONEPSE can be used without bypassing bot protection
or breaking a published ToS.** Scraping Merolagani or the others would violate
the project's (and the sources') access restrictions. Recommend: stay on YONEPSE raw
+ use ShareHub test-mode if (and only if) the owner is willing to test sub-hourly
with X-DataApi-Test: true.

## Additional candidate — `basic-bgnr/NepseUnofficialApi` (user-provided)

Inspected the actual README on 2026-10-16.

- **Nature:** "Unofficial library to interface with nepalstock.com — *Deciphers the authentication key to access the API*." It (a) strips the WASM obfuscation, **(b) requires `nepse.setTLSVerification(False)` as its documented usage**, i.e. explicitly disables TLS verification, and (c) shipped a `NepseServer.py` Flask server that exposes more of the same.
- **Relevant quote:** *"`setTLSVerification(False)` — This is temporary, until Nepse sorts its ssl certificate problem"* and *"The mistake is primarily due to Nepse as it means that the certificate chain used by Nepse is incomplete"* and recommends adding CA certs from ssllabs.
- **Our evidence contradicts its premise:** we performed a verified TLS handshake against `nepalstock.com.np:443` (DigiCert/GeoTrust, valid 2025-12-12 → 2026-12-10, SAN covers the host, *certificate verify result = OK*). TLS works; the cert chain is complete. The library's *documented* usage — disabling TLS verification — is exactly what our safety rules forbid (`"Never ... bypass authentication, anti-bot controls, rate limits ... Disable TLS verification"`). Its recommended fix is to trust an upstream-wasm-stripped token without verifying the exchange cert.
- **Verdict:** NOT ADOPT. We already resolved the auth by *not* using this chain at all; TLS verification stays on. This library adds nothing permitted and actively instructs the opposite of our hard rules. Status: `BLOCKED` (would require a policy change *to the safety rules*, not a configuration change).
- Follow-up implication: a usable NEPSE library for "public" data is just the anti-bot bypass again. Same outcome: live official access is not lawfully available to us; YONEPSE (raw) remains the free current-day option.

## Current free-source decision (final)

Permitted-no-auth free options in inventory: YONEPSE raw content (~30–76 min), binayabaral daily (historical), plus YONEPSE annual/financial/dividend/corporate-action datasets.

**Recommendation:** stay on the existing legit path (YONEPSE raw + nightly `megatool fetch` of binayabaral) and honestly labelled delayed data. The Go library integration's **wiring remains intact but live = BLOCKED** until the owner (a) opts into the anti-bot harness explicitly or (b) licenses a sanctioned feed. No bugfix was possible within policy this pass. Tests still at 2200 pass.
