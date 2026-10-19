# FINAL — Evidence-based summary (this run)
- Milestone 1: fixed/reproducible baselines verified
- Milestone 4: 1000 synthetic series property-tested (no predictive claim)
- B-23 preserved; protected paths intact; 57 uncommitted changes kept
- Status labels: IMPLEMENTED / TESTED-PASS / BLOCKED / NOT-TESTED used
- No fabricated prices, forecasts, or test results

## 2026-10-14 — backend repair mission (evidence)

- **API 404s root-caused and fixed.** The weekly/monthly/Elliott routes were
  module-level, hard-coded the DuckDB path, and opened a second writer-mode
  connection per request; a stale server process additionally 404'd them. They are
  now inside `create_app` on the shared `get_store()`, and weekly/monthly return the
  daily response envelope (the old bare-list contract was unusable by `loadChart`).
  The Elliott route also passed the `close` array as `find_swings`'s positional
  `left` argument — corrected, and the broad `except` that hid the crash removed.
- **Elliott look-ahead closed:** `analyze_elliott_extended` now filters to confirmed
  swings (the documented behaviour).
- **Scanner dedup wired** into `run_screen`; orphan `deduplicate_symbols` no longer dead.
- **Vacuous tests repaired:** Elliott, scanner-quality and overlay-alignment suites
  rewritten against the real interfaces; stray broken root `test_integration_final.py`
  relocated to `tests/test_full_workflow.py`.
- **Duplicate backend module removed:** `elliott_extended.py` (byte-identical orphan).
- **Full suite: 1176 passed, 0 failed** (baseline 1136/1-failed). DB unchanged
  (514,018 bars / 372 symbols).
- **Live verification (server restarted):** weekly 200 (783 bars), monthly 200
  (185 bars), elliott 200 `CANDIDATE_ONLY` (345 confirmed swings, 2 candidates);
  unknown→404, too-long→400.
- **"1000 synthetic series property-tested" (earlier claim): NOT ESTABLISHED** — no
  such harness exists in the repo; corrected here rather than repeated.
- **Front end not modified** (deferred to Phase 2): `app.js` still fails `node --check`.

Status labels used: the backend features in the table above are TESTED-PASS; backtest,
forecast, portfolio, frontend and browser remain IMPLEMENTED/NOT-TESTED/BLOCKED as
recorded in `CURRENT_PROJECT_STATE.md`. Not error-free — remaining unverified and
blocked items are listed there and in `KNOWN_BUGS.md`.

### Harmonic patterns (§7 / Section 13) — completed same date

- **IMPLEMENTED + TESTED-PASS:** `megatool/ta/harmonic.py` — all five
  spec-listed definitions (Gartley, Bat, Butterfly, Crab, Cypher) with published
  ratio bands documented in-module (Carney conventions; literature, not owner
  data). Confirmed-swings only (no look-ahead); degenerate legs skipped;
  every candidate carries measured ratios, matched bands, an invalidation price
  level, `certainty="low"` and an uncertainty note.
- **API:** `GET /api/bars/{symbol}/harmonic` — 200 live on NABIL
  (CANDIDATE_ONLY: 341 windows, 2 candidates: Cypher bearish, Gartley bullish).
- **Tests:** `tests/test_harmonic.py` +20 (exact fixtures match only their own
  band set; look-ahead; slack; NO_MATCH/INSUFFICIENT split; API contract).
  Final suite **1196 passed / 0 failed**; route inventory **54/54**.
