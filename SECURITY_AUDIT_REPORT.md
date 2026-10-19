# MEGA TOOL — SECURITY AUDIT REPORT
Audit date: 2026-10-17

## Scope
Static inspection of megatool/api.py, megatool/llm.py, megatool/kronos_service.py,
app.js custom-formula editor. No destructive testing against production.

## Findings
- SQL: parameterized queries used (no raw string interpolation found in inspected paths).
- Secrets: API keys read from env (MEGATOOL_AI_API_KEY), never logged or echoed (llm.py guarantees).
- Custom formula DSL: recursive-descent parser, whitelisted functions/series only; no eval, no globals, no filesystem/network access. Unknown identifiers rejected at parse time. Tested: `window.alert(1)` → "Error: invalid number".
- CORS: configured in api.py (inspect deployment config before exposing publicly).
- Debug endpoints: none found exposed beyond /api/health.
- File paths: index paths constructed from symbol params; verify sanitization (not fully audited).
- Rate limiting: not implemented (acceptable for single-user local; required for public deployment).
- Auth: friend-token mechanism (X-Friend-Token) for gated sources; not a full user-auth system.

## Remaining concerns
- No rate limiting on expensive endpoints (Kronos inference, LLM calls).
- No CSRF protection if deployed with cookie auth (currently token header).
- Dependency CVEs not audited (pip audit not run).
- Formula editor resource limits (infinite loops): bounded by input length (bars array), but a deeply nested formula could be expensive — not stress-tested.

## Recommendation
Run `pip audit` and a dependency review before public deployment. Add rate limiting for inference endpoints.