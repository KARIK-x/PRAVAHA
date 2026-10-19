# MEGA TOOL — DEPLOYMENT READINESS REPORT
Audit date: 2026-10-17

## Verdict: NOT READY for unattended production deployment.
Works locally (dev :10000) and the isolated dev environment. Several
external dependencies and data-rights items remain unresolved.

## A. Works locally (dev server)
- FastAPI app serves API + static assets on 127.0.0.1:10000.
- 2331 backend tests pass.
- Frontend syntax checks pass.
- Kronos inference works on Apple Silicon (MPS).

## B. Requires external services / credentials
- LLM providers: Ollama (local install + model pull) or OpenRouter (MEGATOOL_AI_API_KEY). Default disabled (safe).
- Live NEPSE feed: gated; 17 sources marked review_required. Not activated.
- go-nepse provider: authorization-gated, not probed as authorized.

## C. Required environment / paths
- MEGATOOLDATADIR (or default data dir) must point at a writable location with bars, models, DBs.
- data/models/ must contain Kronos weights + tokenizers (~32 MB per variant used).
- Writable dirs for DBs, logs, cache.

## D. Not tested
- Production-like (gunicorn/uvicorn behind reverse proxy) smoke test.
- Multi-worker concurrency.
- Cold-start model loading under memory pressure (8 GB M1).
- CORS under a real origin.
- Auth/session flows under HTTPS.

## E. Risks
- Frontend cache-buster must bump on every change (?v=d34 currently).
- 218 uncommitted files; no commits without owner authorization.
- Kronos first-run loads weights (seconds) — needs loading UX (implemented).
- Dev/prod must stay isolated (port 8710 prod, 10000 dev).

## F. Blockers before deployment
1. Resolve market-data access (live feed gated) or ship historical-only with honest labeling (already labeled).
2. Decide on LLM provider (Ollama/OpenRouter) or ship disabled.
3. Production-like smoke test + health check.
4. Backup/restore procedure for DBs.