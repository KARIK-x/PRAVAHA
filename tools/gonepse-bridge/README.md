# gonepse-bridge

A thin, JSON-speaking command-line wrapper around the **actual**
[`github.com/voidarchive/go-nepse`](https://github.com/VoidArchive/go-nepse)
Go library. Mega Tool's Python backend runs it as a subprocess and reads the
single JSON object it prints to stdout.

This is the real Go library — not a Python re-implementation of its protocol.
The pinned module version is recorded in the response envelope
(`moduleVersion`) alongside the library's own `Version` constant
(`libraryVersion`); the two differ because the library's constant lags the
module tag.

## Why a subprocess

The data source is a Go library. Isolating it behind a process boundary means:

* the Go toolchain is needed only to **build** this binary — the Python
  application never imports Go and never runs the library's WASM/auth code;
* the library's HTTP, retry and token handling stay exactly as the upstream
  author wrote them, so what we test is what runs;
* a crash or hang in the Go client cannot take down the Python process.

## Build

```sh
cd tools/gonepse-bridge
go build -o /path/to/gonepse-bridge .
```

Requires Go **1.25+** (the module declares `go 1.25`). The only dependencies
are the library itself and its pure-Go transitive deps (`wazero`,
`golang.org/x/sync`) — there is no CGO, so cross-compilation is trivial.

Point the Python adapter at the binary with the `MEGATOOL_GONEPSE_BIN`
environment variable, or put `gonepse-bridge` on `PATH`.

## Protocol

Reads one JSON object from **stdin**, writes one JSON object to **stdout**.

Request:

```json
{"op": "price-history", "symbol": "NABIL", "start": "2026-01-01", "end": "2026-06-30"}
```

Response:

```json
{"ok": true, "schemaVersion": "1", "op": "price-history",
 "source": "github.com/voidarchive/go-nepse",
 "moduleVersion": "v0.2.5", "libraryVersion": "0.2.0",
 "tlsVerification": true, "data": [ ... ]}
```

On failure `ok` is `false` and `error.kind` is one of the library's own
`ErrorType` values (`network_error`, `unauthorized`, `not_found`,
`rate_limit`, `invalid_server_response`, `token_expired`, …) or one of
`invalid_client_request`, `timeout`, `canceled`, `internal_error`.

### Operations

| `op` | Library call | Needs |
| --- | --- | --- |
| `market-summary` | `MarketSummary` | — |
| `market-status` | `MarketStatus` | — |
| `securities` | `Securities` | — |
| `find-security` | `FindSecurityBySymbol` | `symbol` |
| `live-market` | `LiveMarket` | — |
| `price-history` | `PriceHistoryBySymbol` | `symbol`, `start`, `end` |
| `nepse-index` | `NepseIndex` | — |
| `sub-indices` | `SubIndices` | — |
| `company` | `CompanyBySymbol` | `symbol` |
| `company-profile` | `CompanyProfileBySymbol` | `symbol` |
| `dividends` | `DividendsBySymbol` | `symbol` |
| `floorsheet` | `FloorSheetBySymbol` | `symbol`, `date` |
| `market-depth` | `MarketDepthBySymbol` | `symbol` |

## TLS

Certificate verification is **enabled** (`Options.TLSVerification = true`) and
is never turned off by this bridge. Upstream's own docs set it to `false`
because NEPSE's certificate chain is awkward; that is a problem to *diagnose*,
not to bypass. If a live call fails with a certificate error, the error is
reported verbatim in `error.message`.

## Authorization gate

When the target host is the real NEPSE API, the bridge refuses to run unless
`MEGATOOL_NEPSE_API_AUTHORIZED=1` is set, and prints
`{"error":{"kind":"unauthorized"}}` with exit code `3`. A non-default base URL
(a local test server or proxy) is not gated. The Python adapter enforces the
same gate before spawning the process, so the checks are independent.

## Library quirks worth knowing

* **`Options.BaseURL` is ignored.** Every request (including the token
  endpoint) is built from `Options.Config.BaseURL`. The bridge sets both, but
  only `Config.BaseURL` has an effect.
* `nepse.Version` reports `0.2.0` at module tag `v0.2.5`.
* The client sends a browser `User-Agent` (upstream's choice) and obtains an
  anonymous token from `/api/authenticate/prove`, stripping obfuscating
  characters via an embedded WASM module. That behaviour belongs to the
  upstream library; this bridge does not add, remove or extend it.

## Tests

```sh
go test ./...
```

The tests exercise the library **for real** — token acquisition, the embedded
WASM salt parse, the `Authorization: Salter …` header, and JSON decoding —
against a local `httptest` TLS server serving the library's own token fixture
and canned market data. No request is made to NEPSE. The test injects the test
server's trusted HTTP client, so TLS verification semantics are unchanged.
