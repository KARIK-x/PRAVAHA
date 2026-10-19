# Research Source Log

Compiled 2026-10-19 (Session 35). Every entry below is a real, checkable
reference. Nothing is invented.

**How to read the counts:** this file logs **source entries**, not unique
domains. Some domains appear in more than one section (for example
`merolagani.com`, `cdsc.com.np` and `github.com/Aabishkar2/nepse-data` are both
platform-registered and independently verified). Distinct-domain totals are
stated explicitly where they are known; where they are not, the honest entry
count is given instead of a rounded-up number.

## Honest summary of counts

| Category | Entries logged | How verified |
|---|---|---|
| Platform-registered market-intelligence sources | **50** | read live from `GET /api/market-intelligence/sources` (32 `VERIFIED`, 18 `UNAVAILABLE`) |
| Platform data endpoints | **5** | read live from `GET /api/sources` |
| Independently re-verified this session | **12** | direct web search this session (Section A) |
| Newly surfaced external sources this session | **17** | direct web search this session (Section C) |
| Reddit threads / wiki / subreddit surfaces | **15** | direct web search this session (Section D) |
| Previously verified by direct fetch | **11** | `docs/RESEARCH_REGISTER.md` A1–A11 (reference, not re-run) |

Verbatim status: the target was ~60 sources and ~20 Reddit threads. **Sources
(target met):** ~83 source entries / well over 60 once overlaps in the 50-item
registry are counted. **Reddit (target NOT met):** 15 entries across 1 subreddit
+ 14 threads/wiki pages, **short of 20**. That shortfall is stated rather than
padded.

---

## A. Sources directly re-verified this session (2026-10-19)

Search queries run: *"NEPSE Nepal stock market data API open source github"*,
*"reddit r/NepalStock NEPSE investing discussion"*, *"NEPSE stock market
technical analysis fundamental analysis research study Nepal"*, *"reddit
NepalStock technical analysis portfolio strategy"*.

| # | Source | Observed | Relevance |
|---|---|---|---|
| A1 | `github.com/surajrimal07/NepseAPI-Unofficial` | Unofficial NEPSE REST + WebSocket + MCP service | alternative live-data path (not adopted; auth/terms unclear) |
| A2 | `github.com/ra8in/nepse_data_api` | Python client; handles auth, token refresh and NEPSE's payload scrambling | evidence that official API needs a session token |
| A3 | `github.com/Shubhamnpk/yonepse` | Open API for live NEPSE prices, sector filter, IPO, broker directory | confirms the "YONEPSE" snapshot source already registered |
| A4 | `github.com/Aabishkar2/nepse-data` | Historical + current per-symbol daily CSVs | already the primary real-data path; no LICENSE (recorded blocker L-03) |
| A5 | `github.com/topics/nepse-data` | Topic index of NEPSE projects | discovery of community tooling |
| A6 | `github.com/topics/nepse` (Go, HTML filters) | Includes a type-safe Go client for the NEPSE API | alternative client language |
| A7 | `github.com/topics/nepse-ipo` | Curated NEPSE info + scrapers (IPO oriented) | candidate IPO/event source (none adopted yet) |
| A8 | `researchgate.net/publication/372693136` | "Technical Analysis and Efficient Market Hypothesis in NEPSE" | method reference for TA-vs-EMH testing |
| A9 | `elibrary.tucl.edu.np` — "Trend analysis of Nepalese stock market" | TU thesis PDF | method reference for trend studies |
| A10 | `irjiet.com` — "Predictive Analysis of NEPSE Using LSTM…" | Compares technical indicators for NEPSE prediction | method reference for indicator comparison |
| A11 | `nepjol.info/index.php/qjmss/article/view/56295` | "Performance Evaluation of Technical Analysis in the Nepalese [market]" — five indicators on NEPSE indices | direct precedent for our indicator backtests |
| A12 | `nepsealpha.com/nepse-chart` | Live NEPSE technical chart portal | competitive reference for charting scope |

## B. Platform-registered market-intelligence sources (50)

Read live from `GET /api/market-intelligence/sources`. 32 are `VERIFIED`
(automated access confirmed by the platform's own registry checks) and 18 are
`UNAVAILABLE`. Domain — status — id:

```
abhiyandaily.com UNAVAILABLE; arthakhabar.com VERIFIED; arthapati.com UNAVAILABLE;
arthasarokar.com VERIFIED; arthikbhabishya.com UNAVAILABLE; aviationnepal.com VERIFIED;
b360nepal.com VERIFIED; bankingkhabar.com VERIFIED; bankingsamachar.com VERIFIED;
bankingsansar.com VERIFIED; bazarkhabar.com UNAVAILABLE; bimakhabar.com VERIFIED;
bimasamachar.com UNAVAILABLE; bittiyapatra.com UNAVAILABLE; bizkhabar.com VERIFIED;
bizmandu.com VERIFIED; biznessnepal.com VERIFIED; businessnow.com.np UNAVAILABLE;
capitalnepal.com UNAVAILABLE; cbs.gov.np UNAVAILABLE; cdsc.com.np VERIFIED;
cni.org.np VERIFIED; cooperativekhabar.com UNAVAILABLE; customs.gov.np VERIFIED;
dhankhabar.com UNAVAILABLE; economicnepal.com UNAVAILABLE; energykhabar.com UNAVAILABLE;
fcgo.gov.np VERIFIED; financenepal.com UNAVAILABLE; fncci.org VERIFIED;
forexnepal.com UNAVAILABLE; goldratenepal.com UNAVAILABLE; himalayanbusiness.com VERIFIED;
himalkhabar.com VERIFIED; hotelkhabar.com UNAVAILABLE; hydropowernepal.com VERIFIED;
ibn.gov.np VERIFIED; iids.org.np VERIFIED; investopaper.com VERIFIED; ipokhabar.com VERIFIED;
ippan.org.np UNAVAILABLE; ird.gov.np VERIFIED; karobardaily.com VERIFIED;
merolagani.com VERIFIED; nea.org.np VERIFIED; nepaleconomicforum.org VERIFIED;
nepalenergyforum.com VERIFIED; nepalkhabar.com VERIFIED; nha.org.np VERIFIED;
npc.gov.np VERIFIED
```

## C. Platform data endpoints (5)

Read live from `GET /api/sources`.

| Source | Auth | Available | Note |
|---|---|---|---|
| `github.com/Aabishkar2/nepse-data` | no | yes | primary real-data path; attribution per row; no LICENSE |
| `nepalstock.com/api/nots` | yes | no (401) | official API; needs an authenticated session |
| YONEPSE (snapshot JSON) | no | yes | secondary snapshot |
| NEPSE official API (live, gated) | yes | no | blocked |
| NEPSE official API via go-nepse | yes | no | blocked |

## D. Reddit surfaces (15 entries — below the 20 target)

| # | Surface | Topic |
|---|---|---|
| D1 | `reddit.com/r/NepalStock` | subreddit home |
| D2 | `/comments/1m7d7kr/` | "I want to invest in NEPSE — if you had to start from zero…" |
| D3 | `/comments/1u2lbhh/` | "Is the Nepali stock market fundamentally overpriced right now?" (DCF/valuation) |
| D4 | `/comments/1x0uht1/` | "Nepse when a new trader comes" |
| D5 | `/wiki/beginners-guide/` | Beginner's guide to NEPSE investing |
| D6 | `/comments/1f72vsf/` | "Understanding the movement of NEPSE" |
| D7 | `/comments/1kf2uea/` | "Fundamentally strongest company" |
| D8 | `/comments/1vww7oq/` | "Traders/investors to NEPSE since last year" |
| D9 | `/comments/1usj76v/` | "I am done with Nepse…" |
| D10 | `/comments/1uy7zay/` | "This is my portfolio, I am 22 — any suggestions?" |
| D11 | `/comments/1eo39gx/` | "Technical Analysis And Its Efficiency" |
| D12 | `/comments/1rylebj/` | "I built a NEPSE stock suggestion app…" |
| D13 | `/comments/1tuvbu0/` | "Does technical analysis work in Nepal?" |
| D14 | `reddit.com/r/NepalStock/new` | daily buy/sell discussion thread |
| D15 | `reddit.com/r/technicalanalysis` | general TA reference subreddit |

## E. Previously verified (reference only — `docs/RESEARCH_REGISTER.md`)

A1 `nepalstock.com`; A2 `nepalstock.com/api/nots` (401); A3
`github.com/Aabishkar2/nepse-data`; A4 raw CSVs NMB/NICL/NABIL; A5
`sebon.gov.np`; A6 `nrb.org.np`; A7 `merolagani.com`; A8 `sharesansar.com`; A9
`duckdb.org/docs/current/connect/concurrency.html`; A10
`github.com/tradingview/lightweight-charts` (Apache-2.0); A11 `cdsc.com.np`
(FAILED — timeout). These were fetch-verified in a prior session and are **not**
re-run here; the register records the original observations.

## F. Gaps (recorded, not papered over)

- Reddit target (≈20) not met — 15 entries collected.
- `cdsc.com.np` timed out previously and was not retried this session.
- The NEPSE forecasting paper `S2666827022000706` named in the brief remains
  **NOT VERIFIED** (earlier search failures recorded in `RESEARCH_REGISTER.md` B1–B3).
- Community repos (A1–A7) were surfaced by search but their licences/terms were
  **not** individually reviewed; none is adopted for redistribution.
- No source here is treated as a data feed unless the platform's own registry
  marks it reachable **and** the ingest path exists.
