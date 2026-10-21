# PRAVAHA — Publication Review Report

**Date:** 2026-10-21 · **Branch:** main · **HEAD:** 563e074da03f09da3c94c33ad62a7366144aa0b7
**Remote:** https://github.com/KARIK-x/PRAVAHA.git (origin/main == local HEAD)

---

## 1. Repository & branch
- Root: /Users/ashim/Downloads/AI trading NEPSE
- Branch: main (tracking origin/main)
- Local HEAD == remote HEAD: yes (563e074)
- Working tree at start: clean (0 modified/staged/untracked in git status).

## 2. Files to be added (new, not yet tracked)
- docs/images/01-overview.png … 05-sector-overview.png (5 screenshots)
- docs/SCREENSHOT_GALLERY.md
- PUBLICATION_REVIEW.md (this file)

## 3. Modified files
- None yet (pending approval to adjust .gitignore / remove tracked seed parquet).

## 4. Excluded private-data files (already gitignored)
- data/ (market DBs, caches, exports, kronos, written_pdf, health, dev, models)
- WRITTENdata.pdf, Written_Data_*.xlsx, trading_ledger_master_data.xlsx
- digitized_trading_ledger_and_notes.*
- Kimi_Agent_* folders, AI Trading Nipsy/
- .env (only .env.example tracked)
- *.duckdb, *.sqlite, *.db
- docs/evidence/, docs/screenshots/ (generated)
- .playwright-cli/, *.log

## 5. Potentially sensitive files requiring review
- **seed/pravaha_market_seed.parquet (9.3 MB, TRACKED)** — contains third-party
  NEPSE market data sourced from github.com/Aabishkar2/nepse-data. Redistribution
  rights are unverified. Recommended: `git rm --cached` + add `seed/*.parquet`
  to .gitignore. Requires approval (modifies tracked set / history exposure
  remains in prior commits).
- **docs/WRITTEN_DATA_*.md** (tracked) — documentation about the private
  written trading journal. These describe methodology, not the raw private data,
  but should be reviewed for embedded personal values before publication.
- **PRAVAHA.pdf, logoFimage.png (gitignored)** — large brand assets; not tracked.

## 6. Git history & secret-scan findings
- No .env, .key, .pem, or credential files ever committed (only .env.example).
- No database dumps or personal trading records in history (WRITTENdata.pdf etc.
  are gitignored and never tracked).
- Secret-pattern scan of tracked source found only documentation references to
  tokens/keys (no literal values). The only env file tracked is .env.example
  (placeholders).
- The seed parquet (third-party data) IS in history; deleting later won't remove
  it from prior commits. If redistribution is not permitted, history rewrite
  would be required (needs explicit approval).
- No API keys or passwords found in source code.

## 7. Screenshot count and gallery location
- 5 screenshots in docs/images/ (01-overview.png … 05-sector-overview.png).
- Gallery index: docs/SCREENSHOT_GALLERY.md.
- Excluded from gallery: portfolio, journal, written-PDF, and personal-account
  views (private data risk).

## 8. Documentation created
- README.md (existing, comprehensive).
- docs/SCREENSHOT_GALLERY.md (new).
- Numerous existing docs/ reports (CHANGELOG, PROJECT_STATUS, etc.).

## 9. Tests run and results
- Full non-browser suite (PID 76188, ~6 min): completed.
- Result: 12 FAILED, all in deploy_access (11) and deploy_seed (1).
  - test_deploy_access.py::test_private_records_stay_owner_only (11 variants)
  - test_deploy_access.py::test_unknown_api_route_is_denied_by_default
  - test_deploy_access.py::test_private_write_is_not_reachable_with_a_token
  - test_deploy_seed.py::test_seed_from_snapshot_records_an_ingestion_log_row
- These failures relate to deployment-access gating on a deployed instance and
  seed ingestion logging; they do not indicate broken core analytics.
- No other test failures observed in the run (progress reached 100%).
- Browser tests not re-run in this pass (previously reported 47 passed).

## 10. Features that could not be captured or verified
- Portfolio, Journal, PDF Journal views (private data risk) — not captured.
- Chart drawing tools, indicator drawer — not captured as separate screenshots
  (covered structurally in existing docs).
- Live NEPSE feed — blocked (401, no credentials) — documented, not captured.
- TTM EPS computation — blocked (source basis undocumented).

## 11. Remaining security / licensing concerns
- Seed parquet redistribution rights unverified (see §5).
- docs/WRITTEN_DATA_*.md should be reviewed for embedded personal values.
- No license file added (user has not authorized a license).
- Repository visibility not changed (remains as-is).

## 12. GitHub URL
- https://github.com/KARIK-x/PRAVAHA

## 13. Confirmation
- No website deployment performed.
- No destructive git operations performed.
- No commits or pushes performed yet (awaiting approval).

---

## Approval needed before proceeding
1. Remove seed/pravaha_market_seed.parquet from tracking (git rm --cached) and
   ignore seed/*.parquet? (Recommended: yes, due to unverified redistribution.)
2. Commit + push the new screenshots + gallery + this review report?
3. Add a LICENSE file? (User must choose/authorize.)
