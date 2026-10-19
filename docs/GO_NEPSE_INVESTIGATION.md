# go-nepse — investigation and integration decision

> **Update — session 22 (supersedes the headline below).** The owner directed that
> the **actual** `github.com/voidarchive/go-nepse` Go library be integrated, not a
> Python re-implementation of its protocol. It now is, behind a process boundary and
> with the project's hard rules intact: TLS verification stays **ON**, and every live
> call stays behind the existing `MEGATOOL_NEPSE_API_AUTHORIZED` gate. See **§11**.
> Sections §1–§10 below are the original investigation and remain as the record of
> why a *naive* (ungated, TLS-off) adoption was rejected — that conclusion still
> holds. Where they read "do not integrate", read "do not adopt it as an ungated
> live source".

**Question asked:** can [`github.com/VoidArchive/go-nepse`](https://github.com/VoidArchive/go-nepse)
be used as a data source for Mega Tool?

**Answer: NO — do not integrate.** The library is a competent piece of Go
engineering, but it obtains its data by defeating NEPSE's anti-automation
controls on the *official* production API and by disabling TLS certificate
verification. Adopting it would breach Mega Tool's own hard rules (never bypass
an authorization gate; never disable TLS verification; keep collection behind
`MEGATOOL_NEPSE_API_AUTHORIZED`).

This document records the evidence. **No live request was made to
`nepalstock.com.np` or any NEPSE endpoint during this investigation** — that
would itself be the bypass the gate exists to prevent. Everything below comes
from static inspection of the published source.

## 1. Repository facts

| Field | Value | Source |
|---|---|---|
| Repo | `github.com/VoidArchive/go-nepse` | repo page |
| Language | Go | repo page |
| License | MIT | `LICENSE`, repo sidebar |
| Latest version | 0.2.0 (2026-01-03) | `CHANGELOG.md` |
| First release | 0.0.1 (2025-12-30) | `CHANGELOG.md` |
| Commits | 35 | repo page |
| Stars / forks / watchers | 9 / 3 / 0 | repo page |
| Go requirement | **Go 1.25+** | `go.mod`, README |
| Dependencies | `github.com/tetratelabs/wazero v1.9.0`, `golang.org/x/sync v0.16.0` | `go.mod` |
| Tests present | `fundamentals_test.go`, `transport_test.go` only | file listing |
| Changelog "Unreleased / Planned" | "Unit tests for core functionality", "Integration tests", "Rate limiting improvements" | `CHANGELOG.md` |
| Known issues | Graph endpoints return empty (server-side); `SubIndices()` returns empty | `CHANGELOG.md`, README |

The project is ~4 months old at the time of review, effectively single-author,
with core unit/integration tests still on the *planned* list — i.e. not yet
written. That is a maintenance and correctness risk on its own, independent of
the policy problems below.

## 2. What it talks to

`config.go`:

```go
const DefaultBaseURL = "https://nepalstock.com.np"
```

Every endpoint is under `/api/nots/...` on the **official NEPSE site**
(`/api/nots/market-summary`, `/api/nots/security`, `/api/nots/nepse-index`,
`/api/nots/nepse-data/floorsheet`, …). These are the same undocumented official
endpoints that Mega Tool's gated official collector is designed around.

Mega Tool rule: *the existence of a client library does not grant authorization
to activate the official collector.* Using go-nepse to fetch data would be a
de-facto activation of that gated surface, with the gate still unset. That is a
hard stop.

## 3. Authentication — an anti-bot reverse-engineering scheme

`internal/auth/manager.go` (package doc, verbatim):

> "Package auth handles NEPSE API authentication using **embedded WASM** to
> decode obfuscated tokens returned by the NEPSE API."

The scheme:

1. `GET /api/authenticate/prove` returns five integer "salts" plus an
   `accessToken` with junk characters inserted and a `serverTime`.
2. An **embedded WebAssembly module** (executed through `wazero`) is called as
   `parser.indicesFromSalts(salts)` to work out *which character positions* to
   strip from the token.
3. `sliceSkipAt` removes those positions; the cleaned token is sent as
   `Authorization: Salter <token>`; tokens are refreshed every 45 s.

So the library reverse-engineers, and ships a binary blob to reproduce, the
token de-obfuscation that NEPSE uses specifically to make scripted access hard.
That is *circumventing an access restriction on a third-party production
system*, which Mega Tool's safety rules forbid outright and which is also a
fragile foundation (the blob is only valid until NEPSE rotates the scheme).

## 4. TLS

`transport.go`:

```go
TLSClientConfig: &tls.Config{
    InsecureSkipVerify: !options.TLSVerification, //nolint:gosec
},
```

and the README's Quick Start sets:

```go
opts.TLSVerification = false // NEPSE servers have certificate issues
```

Out of the box the documentation tells users to turn **certificate
verification off**. Mega Tool's rule is TLS verification **on**, always.
(The README's own "Production Checklist" admits the right answer is "route
through secure proxy", i.e. the library does not solve this itself.)

## 5. Browser impersonation

`transport.go` → `setCommonHeaders` sets a fake Chrome User-Agent, `Sec-Ch-Ua*`
client hints, a spoofed `Host`, `Origin` and `Referer`, with the comment:

> "Some NEPSE endpoints reject requests with non-browser user agents."

Bypassing server-side bot detection by impersonating a browser is exactly the
"bypass access restrictions" behaviour that is prohibited.

## 6. Retry / rate limiting / transport behaviour (for completeness)

* Retry with exponential backoff (`RetryDelay * 2^(attempt-1)`, capped at 30 s)
  on network errors, HTTP 5xx and 429; context cancellation is honoured.
* One automatic re-authentication on HTTP 401.
* `singleflight` collapses concurrent token refreshes.
* Connection pooling (`MaxIdleConns: 100`).
* **No client-side rate limiter** is implemented — the changelog lists "Rate
  limiting improvements" as *planned*. The README's own production checklist
  warns to "respect implicit limits to avoid IP blocks".

## 7. Endpoint coverage (claimed)

Market summary/status/index/sub-indices/live market/supply-demand; securities &
companies; today's prices; `PriceHistory(id, start, end)`; market depth (order
book); floor sheet (day and per-security); top gainers/losers/turnover/trade/
transaction; intraday graph endpoints; and fundamentals (company profile, board
of directors, reports with PE/EPS/book value, corporate actions, dividends).

Coverage is genuinely broad — but it is all *live-official-API* coverage. It
adds essentially nothing to Mega Tool's **historical** capability, and the
mission requires the app to keep working from historical data even when live
connectivity fails.

## 8. Isolated testing performed

| Test | Result |
|---|---|
| Go installed locally? | **No** (`go` not found); not installed by this session |
| Live connectivity to NEPSE | **Not attempted — deliberately** (would require the gated authorization) |
| Auth behaviour | Inspected statically (WASM salt→index stripping, `Salter` header) |
| Market summary / quotes / OHLCV / index / floorsheet / depth | Not exercised; endpoints enumerated from `config.go` |
| Response timestamps / symbol coverage | Not verifiable without a live call |
| TLS certificate validation | Confirmed the library's default path disables it |
| Rate limiting / retries | Retry/backoff read from source; no rate limiter present |
| Behaviour outside market hours | Not tested |

Because Go is not installed and the endpoints are gated, a live test was neither
possible nor permitted. A successful response outside trading hours would in any
case not prove "live" data — the fixture dates confirm how easy it is to mistake
stale bars for current ones.

## 9. Decision and rationale

**Do not integrate. Preserve the existing historical pipeline.** Concretely:

1. **Policy breach.** Integration would activate the gated official NEPSE
   surface without the owner's authorization, via a tool whose entire design is
   to defeat NEPSE's bot controls. Not permitted.
2. **Security.** TLS verification is disabled by default/default-recommended; the
   project rule is verification on.
3. **Architecture.** It would require a Go sidecar service (Go 1.25 + WASM
   runtime) beside the Python backend — a second server the mission says to
   avoid unless clearly justified, for a source that can disappear at any time.
4. **Maturity.** 4-month-old, 0.2.0, ~9 stars, core tests unwritten, two known
   broken endpoint families.
5. **No unique value.** It offers no historical depth Mega Tool lacks, and live
   access remains gated by the owner's ruling regardless.

**What would change this:** an explicit, documented owner decision to authorize
official NEPSE access (`MEGATOOL_NEPSE_API_AUTHORIZED=1`) *and* NEPSE's terms
permitting it. Even then, a hardened adapter would have to keep TLS verification
on and avoid fingerprint spoofing — at which point the value of go-nepse over a
small purpose-built adapter is questionable.

## 10. What Mega Tool keeps instead

* The stored historical daily dataset remains the primary source; every
  analytical feature works from it with no live dependency.
* Data-source health, freshness and provenance continue to be surfaced per
  response (source, `data_as_of`, "not a live feed").
* The official collector stays behind `MEGATOOL_NEPSE_API_AUTHORIZED` (unset)
  plus `MEGATOOL_INTEGRATION_AUTHORIZED` for writes. **No change.**

## 11. Actual Go-library integration (session 22)

The owner asked for the *real* Go library, not a protocol re-implementation, with
the safety rules intact. That is now in the tree.

### 11.1 Shape

| Piece | Path | What it is |
|---|---|---|
| Go bridge | `tools/gonepse-bridge/` | A small Go `main` package that links the real library and speaks one JSON object in / one out |
| Python adapter | `megatool/datasources/gonepse.py` | `GoNepseAdapter(BaseAdapter)` — spawns the bridge, parses the envelope, maps errors |
| Diagnostics route | `GET /api/gonepse/status` | Network-free provider status for the UI/operators |
| Sources listing | `GET /api/sources` | Now includes a `go-nepse` entry |
| Go tests | `tools/gonepse-bridge/main_test.go` | 9 tests exercising the real library against a local `httptest` TLS server |
| Python tests | `tests/test_gonepse_adapter.py` | 21 tests over the adapter contract; `tests/test_api.py` covers the route |

The library is pinned at **module v0.2.5** (`go.mod`). The bridge reports both the
pinned module version and the library's own `nepse.Version` constant (`0.2.0`),
because the two disagree upstream.

### 11.2 Why a subprocess rather than a Python re-implementation

The mission says to use the actual library. Embedding a Go runtime in the Python
process is not possible; re-implementing the protocol in Python is exactly what was
rejected. A subprocess keeps the real library's HTTP/retry/token logic intact (what
runs is what upstream wrote), needs Go only at build time, and isolates any crash or
hang from the Python app.

### 11.3 TLS: verification stays ON — and it passes today

The bridge sets `Options.TLSVerification = true` and never clears it. Upstream's own
docs suggest disabling verification because NEPSE's certificate chain "has issues".
We diagnosed that instead of adopting it. With verification **enabled**:

```
host: nepalstock.com.np:443   verified_handshake: true   tls: TLSv1.2
issuer:  DigiCert Inc / GeoTrust TLS RSA CA G1
subject: NEPAL STOCK EXCHANGE LTD / www.nepalstock.com.np
valid:   Dec 12 2025  ->  Dec 10 2026
SAN:     www.nepalstock.com.np, nepalstock.com, nepalstock.com.np, nots.com.np, ...
```

Evidence: `docs/evidence/session22-nepse-tls-cert.txt`. So the documented cert
problem is **not present** for `nepalstock.com.np` today; a live call would not need
insecure mode. This is a plain TLS handshake (no data request, no token), taken to
diagnose rather than bypass.

### 11.4 The gate is enforced twice

* **Python side** — `GoNepseAdapter.call()` raises `SourceUnavailable` when
  `MEGATOOL_NEPSE_API_AUTHORIZED != "1"` **before** the subprocess is spawned.
* **Go side** — when the target host is the real `nepalstock.com.np`, the bridge
  refuses and exits `3` with `{"error":{"kind":"unauthorized"}}` unless the same env
  var is `1`. A non-default base URL (a test server or proxy) is not gated.

Neither layer can be bypassed by the other, and the adapter never sets the variable.

### 11.5 Operations exposed

`market-summary`, `market-status`, `securities`, `find-security`, `live-market`,
`price-history`, `nepse-index`, `sub-indices`, `company`, `company-profile`,
`dividends`, `floorsheet`, `market-depth` — the priorities the mission listed
(summary, status, lookup, live, history, index, company) plus low-cost extras.

### 11.6 What the tests prove

* **Real library, real auth path.** The Go test server serves the library's own
  token fixture; the test asserts the bridge produced a decoded `MarketSummary` and
  that the mock received an `Authorization: Salter <token>` header — i.e. the token
  fetch, the embedded-WASM salt parse and the auth header all executed. No request
  reaches NEPSE.
* **Error fidelity.** A provider `404` maps to `error.kind == "not_found"`; unknown
  ops and missing symbols map to `invalid_client_request`; `context` deadline maps to
  `timeout`; a rate-limit error keeps its own kind. Nothing is silently swallowed.
* **The gate.** Unauthorized real-host calls are refused at both layers; the Python
  adapter proves the subprocess is *not spawned* when the gate is closed.
* **Honest failure modes.** Malformed JSON, empty output, non-envelope JSON, timeout
  and `OSError` each raise a distinct, truthful error — never a plausible value.
* **Python ↔ Go communication.** With the built binary present, the test runs the
  bridge (gate open) against an unreachable host and requires a parsed provider error
  — exercising the subprocess, the stdin/stdout protocol and the error mapping. With
  the binary absent, the adapter must refuse with a clear reason. Neither branch
  contacts NEPSE.

### 11.7 Live-connection status: BLOCKED (honest)

No live call was made. The owner gate is **unset** in this environment, so both
layers refuse by design. The bridge builds, its Go tests pass, the adapter's Python
tests pass, and TLS verification is confirmed to succeed — but **"the bridge builds
and the mock tests pass" is not, and is not claimed as, "live data works."** A live
connection remains BLOCKED pending the owner's standing authorization ruling, exactly
as for the existing Python official collector.

### 11.8 Remaining limits and quirks

* `Options.BaseURL` is dead code upstream — requests (including the token endpoint)
  use `Options.Config.BaseURL`. The bridge sets both; only the latter matters.
* `nepse.Version` reports `0.2.0` while the module tag is `v0.2.5`.
* The library sends a browser `User-Agent` and strips obfuscating token characters
  via an embedded WASM module. That is upstream's behaviour; the bridge neither adds
  to it nor extends it. It is the reason integration must stay behind the owner gate.
* Historical price rows carry no opening price, so the adapter's `fetch_history`
  leaves `open` null rather than manufacturing it.
* Rate limiting: the library has retries/backoff but no limiter; the adapter declares
  a low `rate_limit_rps` and the mission's "no bypassing rate limits" rule stands.
* Graph endpoints are documented upstream as returning empty, and `SubIndices()`
  returns empty on some responses — carried as known upstream limits.

