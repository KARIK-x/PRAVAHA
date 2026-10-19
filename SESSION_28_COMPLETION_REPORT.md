# Session 28 — completion report (2026-10-18)

Scope: continue the NEPSE Mega Tool charting / TA / research workbench mission on
top of session 27. **No rebuild, no reversal of prior work, no new disconnected
frontend.** The existing app is the source of truth; working features, data and
user configs were preserved.

Status labels used exactly: **IMPLEMENTED** · **TESTED-PASS** · **TESTED-FAIL** ·
**NOT-TESTED** · **BLOCKED** · **APPROXIMATION** · **DATA-DEPENDENT** ·
**NOT IMPLEMENTED (backlog)**.

## Safety envelope actually held

* Production uvicorn on **port 8710 was never signalled** — no kill, no restart,
  no modification. All work was served from `data/dev/release` on
  `http://127.0.0.1:10000`.
* Production DBs and Kronos model weights untouched. No GPU/training work.
* **No commits, no pushes, no deploys.** All work remains uncommitted on `main`
  (HEAD `b6c3659`, ~274 changed paths). No destructive git operations.
* No secrets written to logs or reports. No paid APIs, no infra changes.

## What was delivered (all browser-verified unless noted)

| # | Item | Status | Evidence |
|---|---|---|---|
| 1 | **Market ribbon** — `GET /api/market/ribbon` + scrolling frontend strip: index info, gainers, losers, turnover, volume, 52-week extremes; category headers; clickable; pause/resume; freshness badge | **IMPLEMENTED + TESTED-PASS + DATA-DEPENDENT** | 8 API tests (`tests/test_api.py`); browser: 70 items, 5 groups + 1 honest `unavailable`, badge "NEPSE 2026-10-15 · delayed", pause persists; clicking GBIME opened the chart. `docs/evidence/wb15-ribbon.png` |
| 2 | **Unified chart-object manager** (`Objects` → draggable/resizable `#obj-pane`) listing every visible object with owner, description, visibility, remove | **IMPLEMENTED + TESTED-PASS** | Browser: 6 owner groups, 159→164 rows on NABIL; Hide/Remove verified (9→8, object really gone). `docs/evidence/wb16-objects.png` |
| 3 | **Elliott Wave made visible** — analyze & draw a candidate count, with status line and erase | **IMPLEMENTED + TESTED-PASS** | 5 wave labels + line drawn, `CANDIDATE_ONLY`, viewport unchanged; erase restores manual labels. `docs/evidence/wb17-elliott-drawn.png` |
| 4 | **Active-tool banner** — active tool + anchors placed | **IMPLEMENTED + TESTED-PASS** | "Elliott impulse · 0/5 → 2/5 anchors"; hides on deactivation |
| 5 | **Viewport preserved when adding an indicator** (root cause fixed) | **IMPLEMENTED + TESTED-PASS** | One-directional pane sync + range capture/restore; `{80,200}` preserved for overlay and pane adds. `docs/evidence/wb21-viewport-preserved.png` |
| 6 | **S/R + Fibonacci axis-label crowding** | **IMPLEMENTED + TESTED-PASS** | Label-gap caps; `resistance @ 554 [550-556]` and `zone @ 562` separated |
| 7 | **Indicator registry 81 → 92** (11 new) with info metadata + tests | **IMPLEMENTED + TESTED-PASS** | `megatool/ta/extra.py`; 9 numeric reference tests + sparse property tests; catalogue re-verified "92 of 92 registered". `docs/evidence/wb20-new-indicators.png` |
| 8 | **Documents made reproducible** — reports generator was hard-coded to 81/28/53 | **IMPLEMENTED + TESTED-PASS** | `scripts/generate_indicator_reports.py` now computes counts/placement/verification from the registry and asserts the browser matrix (33/59) |

## Test headline

* **Full suite: 2,660 passed / 0 failed / 0 errors / 0 skipped — exit 0**
  (`$TMPDIR/full_s28.log`; 2,660 passed-dots, 0 `F`/`E`; up +61 on session 27's
  2,599). Command:
  `MEGATOOL_DATA_DIR="$PWD/data/dev/release" .venv/bin/python -m pytest -q -p no:warnings`.
* New this session: 8 ribbon API tests in `tests/test_api.py`; 9 numeric
  reference tests and dedicated sparse-pivot tests for the new indicators in
  `tests/test_indicators.py`.
* Catalogue/audit reproducibility re-established and re-run:
  `scripts/generate_indicator_reports.py` → **92 indicators, 33 overlay / 59 pane,
  49 reference / 41 invariants / 2 sparse / 0 none, 87/92 with a recorded
  reference, 92/92 with a formula.**
* Browser: **0 console errors / 0 warnings** at the end of the verified flows.

## Honesty notes (what is *not* claimed)

* **Verification levels**: 49 `reference` (tested against an independently
  written formula), 41 `invariants` (structural guards only — a floor, not
  numeric proof), 2 `sparse` (`zigzag`, `williams_fractal`, deliberately excluded
  from the dense-series warm-up invariants and covered by dedicated property
  tests). **No indicator is claimed "validated" as a signal on NEPSE.**
* **Approximations disclosed**: Gann fan angles are leg-relative (not absolute
  degrees); circle/ellipse/Fib arc/Fib spiral are polyline approximations. Stated
  in the tools and in `CHART_UX_AUDIT.md` §3.
* **Ribbon** is daily and delayed; `relvol` is `unavailable` (no intraday
  baseline); tickers appear without company names because `security_master` is
  empty in dev. No invented values.
* **Reference-platform gaps** (NEPSE Alpha): a persistent right composition rail
  and a pattern-scanner thumbnail grid are still absent — listed PARTIAL /
  NOT IMPLEMENTED, not faked.

## Blockers / owner decisions (unchanged)

1. **Kronos NABIL GPU fine-tune** — BLOCKED, awaiting explicit owner approval
   (`KRONOS_FINAL_GO_NOGO.md`).
2. **Independent source verification** — only community source
   `github.com/Aabishkar2/nepse-data` (no LICENSE; L-03).
3. **python-dotenv CVE upgrade** — owner decision pending.
4. **Commit / push** — not authorized (~274 uncommitted paths, HEAD `b6c3659`).
5. **Corporate actions** — all prices `unadjusted`; `trading_calendar.json`
   holidays empty.

## Deliverables updated / written this session

* `INDICATOR_CATALOGUE.md` — 92 indicators, Verification section, 33/59 placement.
* `INDICATOR_SOURCE_AND_LICENSE_AUDIT.md` — 92-entry scope, 87/92 references.
* `IMPLEMENTATION_STATUS.md` — session-28 header, rows 4/6/19/25 updated, rows
  26–33 added.
* `CHART_UX_AUDIT.md` — matrix updated to 33/59 and 92; §2 session-28 surfaces;
  §3 tool-by-tool audit vs the reference images.
* `TEST_RESULTS.md` — §28 headline and detail.
* `KNOWN_BUGS.md` — B-100…B-106 (fixed) + session-28 open gaps.
* `REMAINING_BLOCKERS.md` — §20–§22.
* `CHANGELOG.md` — session-28 entry.
* `scripts/generate_indicator_reports.py` — made fully dynamic/reproducible.
* This report.
