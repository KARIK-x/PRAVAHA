# MEGA TOOL — AI MODEL DEPENDENCY MATRIX
Audit date: 2026-10-17 | Source: megatool/llm.py, megatool/agent.py, megatool/kronos_service.py, megatool/api.py

## 1. Kronos (local, primary forecasting model)
- Variants: Mini (Kronos-mini + Kronos-Tokenizer-2k, ctx 2048), Small (Kronos-small + Tokenizer-base, ctx 512), Base (Kronos-base + Tokenizer-base, ctx 512).
- Execution: local, CPU/MPS (Apple Silicon). Weights under data/models/.
- Dependencies: torch 2.14.1, transformers, huggingface_hub (for download only).
- Context limits enforced server-side (VARIANT_MAX_CONTEXT) + Pydantic cap 2048.
- Status: IMPLEMENTED + TESTED-PASS (mini + small + base real inference verified; mini NABIL 2000 ctx = 0.59s; 4000 rejected).
- No network at inference time. No credentials.

## 2. LLM providers (narrative only — never used for prices/calculations)
- Ollama (local): optional, http://localhost:11434. Requires Ollama installed + model pulled. Env: MEGATOOL_AI_PROVIDER=ollama, MEGATOOL_AI_MODEL.
- OpenRouter (hosted): requires MEGATOOL_AI_API_KEY. Env: MEGATOOL_AI_PROVIDER=openrouter.
- Default: DisabledProvider (no network, refuses to run). No paid calls without config.
- Status: IMPLEMENTED, NOT-TESTED live (no credentials in dev). Tests use httpx.MockTransport.

## 3. Other models
- None discovered beyond Kronos + the LLM abstraction. No embedding models, no classifiers, no remote vision models in the quantitative core.
- Agent (megatool/agent.py) routes questions to deterministic tools; LLM interpretation is opt-in (rs-agent-ai checkbox) and sends non-private tool output only.

## 4. Feature-to-model map
- AI Forecaster view: Kronos forecast/evaluate/experiments.
- Research view "Ask": deterministic tools + optional LLM interpretation (hosted/local, named recipient).
- Kronos chart overlay: Kronos forecast on main chart (s19).

## 5. Operational status summary
- Kronos: OPERATIONAL (local weights present, MPS verified).
- Ollama: REQUIRES USER ACTION (install + pull model).
- OpenRouter: REQUIRES CREDENTIALS (MEGATOOL_AI_API_KEY).
- Default state: DISABLED (safe).