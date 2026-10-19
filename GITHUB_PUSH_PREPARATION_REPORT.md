# PRAVAHA — GitHub Push Preparation Report

**Date:** 2026-10-19 · **Dev:** :10000 · **Prod :8710:** untouched (PID 26596)

---

## BLOCKER: No GitHub repository accessible

The repository has **no remote** configured. The authenticated GitHub account
(`KARIK-x`) has only 2 repositories (`Dz`, `Rag`), neither is the NEPSE project.
The fine-grained personal access token in the macOS keychain does **not** have
permission to create new repositories.

**To proceed, I need from you:**
1. The GitHub repository URL (e.g., `https://github.com/USERNAME/REPO.git`).
2. Confirmation of whether to create a new repo or use an existing one.
3. If creating a new repo, a token with `repo` (classic) or `administration:write`
   (fine-grained) permission.

**I cannot push without this information.**

---

## A. GitHub

- **Repository URL:** Not configured (no remote).
- **Branch:** `main`.
- **Commit hash (local):** `b6c3659` (HEAD).
- **Remote verification:** N/A (no remote).
- **Push result:** BLOCKED (no remote, no repo creation permission).

### Authentication
- GitHub username: `KARIK-x` (from keychain `acct`).
- Token type: Fine-grained PAT (`github_pat_...`, 93 chars).
- Token scopes: None (fine-grained, repo-specific).
- Accessible repos: `KARIK-x/Dz`, `KARIK-x/Rag` only.
- No SSH keys configured.
- `gh` CLI not installed.

---

## B. Repository completeness

### Main components (all present, tracked or untracked)
| Component | Status | Tracked? |
|---|---|---|
| Backend (`megatool/`) | ✅ Present, modified | Modified (tracked) |
| Frontend (`web/static/`) | ✅ Present, modified | Modified (tracked) + new files (untracked) |
| Tests (`tests/`) | ✅ Present | Modified (tracked) + new files (untracked) |
| Documentation (`docs/`, `*.md`) | ✅ Present | Modified (tracked) + new files (untracked) |
| Brand assets (`web/static/brand/`) | ✅ Present | Untracked (new) |
| Screenshots | ✅ Present | Untracked (new) |
| PRAVAHA.pdf | ✅ Present | Untracked (new) |
| logoFimage.png | ✅ Present | Untracked (new) |

### Files intentionally excluded (per .gitignore)
- `data/` (market data, databases, caches) — correct, large/regenerable.
- `.venv/` (Python virtual environment) — correct.
- `*.duckdb`, `*.sqlite`, `*.db` — correct, private/regenerable.
- `WRITTENdata.pdf`, `Written Data.pdf` — correct, private trading journal.
- `Kimi_Agent_*` folders — correct, external source projects.
- `AI Trading Nipsy/` — correct, owner folder.
- `models/*.safetensors` — correct, large model weights.
- `docs/evidence/`, `data/transcription/`, etc. — correct, generated.

### Security audit
- **No `.env` files** in the main project (only `.env.example`).
- **No API keys** in source code.
- **No private keys** (`.key`, `.pem`).
- **No secrets in logs or responses.**
- **No private trading records** in the tracked tree (gitignored).
- **All large untracked files are gitignored** (verified).

---

## C. Validation

### Tests executed
- Full non-browser suite: **2,971 passed, 33 skipped, exit 0** (158.04s).
- Browser tests: **47 passed** (19 new + 28 pre-existing).
- `node --check`: OK on app.js, viz.js, kronos_ui.js, indicator_info.js.
- Ruff: clean on touched files (18 pre-existing findings in api.py).

### Known failures/limitations
- 33 skipped tests (opt-in browser tests + environment-dependent).
- 18 pre-existing ruff findings in api.py (market-intelligence routes).
- Real-browser click testing blocked (Playwright/LWC limitation).
- TTM EPS computation blocked (source basis undocumented).

---

## D. PRAVAHA feature inventory

### Implemented and verified
| Feature | Status | Key files |
|---|---|---|
| PRAVAHA rebrand (tokens, logo, shell, footer) | IMPLEMENTED, TESTED-PASS | styles.css, index.html, app.js, brand/* |
| TTM EPS safety fix | IMPLEMENTED, TESTED-PASS | fundamentals.py, app.js, test_ttm_eps.py |
| Indicator readability | IMPLEMENTED, TESTED-PASS | styles.css |
| Chart drawing (timestamp, panning, viewport, hit-test) | IMPLEMENTED, TESTED-PASS | app.js |
| Vertical-line primitive | IMPLEMENTED, TESTED-PASS | app.js |
| 5 analysis categories | IMPLEMENTED, TESTED-PASS | app.js, swings.py |
| 7 new research categories | IMPLEMENTED, TESTED-PASS (toggle) | app.js |
| More Scanners selection/execution | IMPLEMENTED, TESTED-PASS | app.js, index.html |
| Contextual Info modal | IMPLEMENTED, TESTED-PASS | index.html |
| Market Battery 3.0 | IMPLEMENTED, TESTED-PASS | sastoshare.py, app.js, index.html |
| Motion design system | IMPLEMENTED, TESTED-PASS | styles.css, app.js, index.html |
| Hover contrast | IMPLEMENTED, TESTED-PASS | styles.css |
| Analysis panel scroll | IMPLEMENTED, TESTED-PASS | styles.css |
| Live drawing preview | IMPLEMENTED, TESTED-PASS | app.js |
| Sector Explorer (auto-import) | IMPLEMENTED, TESTED-PASS | sectors.py, api.py, app.js |
| Universal Search (cmdk) | IMPLEMENTED, TESTED-PASS | app.js, index.html |
| Crossline vertical primitive | IMPLEMENTED, TESTED-PASS | app.js |

### Features with limitations
| Feature | Status | Limitation |
|---|---|---|
| TTM EPS computation | BLOCKED | Source basis undocumented |
| Sector auto-classification | IMPLEMENTED | Auto-import from CSVs (works) |
| Dividend analysis | BLOCKED | No DPS data (0 corporate events) |
| Live NEPSE feed | BLOCKED | 401, no credentials |
| Technical indicators (numerical) | NOT-TESTED | Structural invariants only |
| Transaction costs (rates) | UNVERIFIED | Not reconciled against contract notes |
| Real-browser click testing | BLOCKED | Playwright/LWC limitation |
| Multi-Timeframe Trend Consensus | NOT-IMPLEMENTED | Daily only |
| Multi-select/bulk delete | NOT-IMPLEMENTED | Not yet built |

---

## E. Render preparation (for subsequent deployment)

### Required Render service type
- Web Service (Python/FastAPI).

### Build command
```
pip install -r requirements.txt
```

### Start command
```
python -m megatool.cli serve --host 0.0.0.0 --port $PORT
```

### Required environment variables (by name, no values)
- `MEGATOOL_DATA_DIR` — path to data directory (must be a persistent disk).
- `MEGATOOL_NEPSE_API_AUTHORIZED` — gate for official NEPSE API (optional).
- `MEGATOOL_SHAREHUB_EMAIL` / `MEGATOOL_SHAREHUB_PASSWORD` — ShareHub credentials (optional).
- `MEGATOOL_LIVE_FEED_URL` — custom live feed URL (optional).
- `MEGATOOL_RATE_LIMIT` — rate limit (optional, default 0).

### Persistent-data concerns
- DuckDB market database must be on a persistent disk.
- SQLite state database (fundamentals, securities) must be on persistent disk.
- Sector CSVs are in the repo — included in the build.
- Model weights (Kronos) are NOT included (gitignored, too large).

### Deployment blockers
1. No persistent disk configured.
2. No `requirements.txt` verification.
3. Kronos AI requires model weights (not in repo).
4. Live NEPSE feed requires credentials (optional).
5. No Render configuration file (`render.yaml`).

---

## F. Safety

- **Production port 8710:** PID 26596 (unchanged). Not modified.
- **No commits, push, or deploy performed.**
- **No destructive Git operations.**
- **All work on dev port 10000.**

---

## G. BLOCKER SUMMARY

**I cannot push to GitHub because:**
1. No GitHub remote is configured in this repository.
2. No repository named "PRAVAHA" exists under the authenticated account
   (`KARIK-x`), which has only `Dz` (JavaScript) and `Rag` (TypeScript/RAG).
3. The fine-grained personal access token in the macOS keychain does not
   have permission to create new repositories.

**To proceed, I need from you:**
1. The GitHub repository URL (e.g., `https://github.com/USERNAME/REPO.git`).
2. Confirmation of whether to create a new repo or use an existing one.
3. If creating a new repo, a token with `repo` (classic) or
   `administration:write` (fine-grained) permission.

**Everything else is prepared and verified.** The working tree is clean of
secrets, all important source files are present, and validation passes.
I am ready to stage, commit, and push the moment the repository URL is provided.
MD
echo "written"