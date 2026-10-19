"""LLM provider tests: hermetic (no network), secret-safe, opt-in only.

These prove the *integration contract* of D1 without contacting any gateway:

* an unconfigured app never dials out — it refuses with an explanation;
* local (ollama) and hosted (openrouter) selection is clean and independent;
* timeouts and connection failures surface as typed errors;
* the API key never appears in a result, an exception, or a status report.

Every HTTP call is served by an ``httpx.MockTransport``; a handler that raises
``AssertionError`` proves "no request was made" for the refusal paths.
"""

from __future__ import annotations

import json

import httpx
import pytest

from megatool import config
from megatool.llm import (
    DisabledProvider,
    LLMNotConfigured,
    LLMRequestError,
    LLMResult,
    LLMUnavailable,
    OllamaProvider,
    OpenRouterProvider,
    get_provider,
    is_configured,
    provider_status,
)

# --------------------------------------------------------------- fixtures / helpers


@pytest.fixture
def cfg(monkeypatch):
    """Isolate the AI_* config knobs for each test (env is read at import)."""

    def _set(**kw):
        for k, v in kw.items():
            monkeypatch.setattr(config, k, v)

    _set(
        AI_PROVIDER="",
        AI_API_KEY="",
        AI_MODEL="",
        OLLAMA_HOST="http://localhost:11434",
        AI_ENDPOINT="",
        AI_TIMEOUT_SECONDS=5.0,
        AI_MAX_TOKENS=64,
    )
    return _set


def _transport(handler):
    return httpx.MockTransport(handler)


def _capturing(handler_calls, response_handler):
    """Wrap a handler so every outgoing request is appended to ``handler_calls``."""

    def _inner(request: httpx.Request) -> httpx.Response:
        handler_calls.append(request)
        return response_handler(request)

    return _transport(_inner)


def _never(request: httpx.Request) -> httpx.Response:  # pragma: no cover - guard
    raise AssertionError(f"a request was made but none was expected: {request.url}")


# --------------------------------------------------------------- disabled by default


def test_no_provider_selected_returns_disabled(cfg):
    cfg(AI_PROVIDER="")
    p = get_provider()
    assert isinstance(p, DisabledProvider)
    assert is_configured() is False


def test_disabled_provider_refuses_without_any_network(cfg):
    """Refusal must happen before a client is even constructed."""
    cfg(AI_PROVIDER="")
    p = get_provider(transport=_transport(_never))
    with pytest.raises(LLMNotConfigured) as exc:
        p.complete("hi")
    assert "No AI provider configured" in str(exc.value)
    assert "quantitative core" in str(exc.value)  # tells the caller it's optional


def test_unknown_provider_is_an_error_not_a_silent_disable(cfg):
    cfg()
    with pytest.raises(LLMNotConfigured) as exc:
        get_provider("omni-router")
    assert "omni-router" in str(exc.value)


# --------------------------------------------------------------- selection is clean


def test_ollama_selection_builds_ollama_provider(cfg):
    cfg(AI_PROVIDER="ollama", AI_MODEL="llama3.2")
    p = get_provider()
    assert isinstance(p, OllamaProvider)
    assert p.name == "ollama" and p.model == "llama3.2"


def test_openrouter_selection_builds_openrouter_provider(cfg):
    cfg(AI_PROVIDER="openrouter", AI_MODEL="m", AI_API_KEY="sk-test")
    p = get_provider()
    assert isinstance(p, OpenRouterProvider)
    assert p.name == "openrouter" and p.model == "m"


# --------------------------------------------------------------- ollama


def test_ollama_happy_path_parses_content_and_usage(cfg):
    cfg(AI_PROVIDER="ollama", AI_MODEL="llama3.2")

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["model"] == "llama3.2"
        assert body["stream"] is False
        assert body["options"]["num_predict"] == 64  # AI_MAX_TOKENS default
        assert body["messages"][-1]["content"] == "say hi"
        return httpx.Response(
            200,
            json={
                "model": "llama3.2",
                "message": {"role": "assistant", "content": "hi"},
                "done": True,
                "prompt_eval_count": 5,
                "eval_count": 7,
            },
        )

    p = get_provider(transport=_transport(handler))
    res = p.complete("say hi")
    assert res.text == "hi"
    assert res.provider == "ollama" and res.model == "llama3.2"
    assert res.prompt_tokens == 5 and res.completion_tokens == 7
    assert isinstance(res, LLMResult)


def test_ollama_without_model_refuses_before_request(cfg):
    cfg(AI_PROVIDER="ollama", AI_MODEL="")
    p = OllamaProvider("", transport=_transport(_never))
    with pytest.raises(LLMNotConfigured) as exc:
        p.complete("x")
    assert "MEGATOOL_AI_MODEL" in str(exc.value)


def test_ollama_connection_refused_is_unavailable(cfg):
    cfg(AI_PROVIDER="ollama", AI_MODEL="llama3.2")

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused", request=request)

    p = OllamaProvider("llama3.2", transport=_transport(refuse))
    with pytest.raises(LLMUnavailable) as exc:
        p.complete("x")
    assert "cannot reach" in str(exc.value)


def test_ollama_timeout_is_unavailable(cfg):
    cfg(AI_PROVIDER="ollama", AI_MODEL="llama3.2")

    def slow(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("read timed out")

    p = OllamaProvider("llama3.2", transport=_transport(slow))
    with pytest.raises(LLMUnavailable) as exc:
        p.complete("x")
    assert "timed out" in str(exc.value)


def test_ollama_bad_payload_is_request_error(cfg):
    cfg(AI_PROVIDER="ollama", AI_MODEL="llama3.2")
    p = OllamaProvider(
        "llama3.2", transport=_transport(lambda r: httpx.Response(200, json={"nope": 1}))
    )
    with pytest.raises(LLMRequestError):
        p.complete("x")


# --------------------------------------------------------------- openrouter


def test_openrouter_happy_path_sends_bearer_and_parses(cfg):
    cfg(AI_PROVIDER="openrouter", AI_MODEL="org/model", AI_API_KEY="sk-secret-key-123")
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "model": "org/model",
                "choices": [{"message": {"role": "assistant", "content": "ok"}}],
                "usage": {"prompt_tokens": 9, "completion_tokens": 3},
            },
        )

    p = get_provider(transport=_transport(handler))
    res = p.complete("q")
    assert res.text == "ok" and res.provider == "openrouter"
    assert res.prompt_tokens == 9 and res.completion_tokens == 3
    # The key travelled in the Authorization header ...
    assert seen[0].headers["Authorization"] == "Bearer sk-secret-key-123"
    # ... but never leaks into the result payload.
    assert "sk-secret-key-123" not in json.dumps(res.__dict__)


def test_openrouter_without_key_refuses_before_any_request(cfg):
    cfg(AI_PROVIDER="openrouter", AI_MODEL="org/model", AI_API_KEY="")
    p = OpenRouterProvider("org/model", api_key="", transport=_transport(_never))
    with pytest.raises(LLMNotConfigured) as exc:
        p.complete("q")
    assert "MEGATOOL_AI_API_KEY" in str(exc.value)
    assert "No request was made" in str(exc.value)


def test_openrouter_key_is_redacted_from_error_body(cfg):
    cfg(AI_PROVIDER="openrouter", AI_MODEL="m", AI_API_KEY="sk-super-secret")

    def echo(request: httpx.Request) -> httpx.Response:
        # Simulate an upstream that echoes credentials back in the error body.
        return httpx.Response(401, text="invalid key sk-super-secret supplied")

    p = OpenRouterProvider("m", api_key="sk-super-secret", transport=_transport(echo))
    with pytest.raises(LLMRequestError) as exc:
        p.complete("q")
    msg = str(exc.value)
    assert "sk-super-secret" not in msg
    assert "[redacted]" in msg
    assert "401" in msg


def test_openrouter_timeout_is_unavailable(cfg):
    cfg(AI_PROVIDER="openrouter", AI_MODEL="m", AI_API_KEY="k")

    def slow(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out")

    p = OpenRouterProvider("m", api_key="k", transport=_transport(slow))
    with pytest.raises(LLMUnavailable):
        p.complete("q")


def test_openrouter_no_choices_is_request_error(cfg):
    cfg(AI_PROVIDER="openrouter", AI_MODEL="m", AI_API_KEY="k")
    p = OpenRouterProvider(
        "m", api_key="k", transport=_transport(lambda r: httpx.Response(200, json={}))
    )
    with pytest.raises(LLMRequestError) as exc:
        p.complete("q")
    assert "no choices" in str(exc.value)


def test_openrouter_uses_configured_endpoint_override(cfg):
    cfg(
        AI_PROVIDER="openrouter",
        AI_MODEL="m",
        AI_API_KEY="k",
        AI_ENDPOINT="https://proxy.internal/v1",
    )
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "x"}}], "model": "m"})

    p = OpenRouterProvider("m", api_key="k", transport=_transport(handler))
    p.complete("q")
    assert str(seen[0].url) == "https://proxy.internal/v1/chat/completions"


# --------------------------------------------------------------- is_configured / status


@pytest.mark.parametrize(
    "provider,model,key,expected",
    [
        ("", "", "", False),
        ("ollama", "", "", False),
        ("ollama", "llama3.2", "", True),
        ("openrouter", "", "k", False),
        ("openrouter", "m", "", False),
        ("openrouter", "m", "k", True),
    ],
)
def test_is_configured_matrix(cfg, provider, model, key, expected):
    cfg(AI_PROVIDER=provider, AI_MODEL=model, AI_API_KEY=key)
    assert is_configured() is expected


def test_provider_status_reports_presence_and_length_not_the_value(cfg):
    secret = "sk-live-abcdef1234567890"
    cfg(AI_PROVIDER="openrouter", AI_MODEL="m", AI_API_KEY=secret)
    status = provider_status()
    assert status["has_api_key"] is True
    assert status["api_key_length"] == len(secret)
    assert status["configured"] is True
    # The value itself must never be serialisable out of the status.
    assert secret not in json.dumps(status)


def test_provider_status_when_disabled_is_harmless(cfg):
    cfg(AI_PROVIDER="", AI_API_KEY="")
    status = provider_status()
    assert status["provider"] == "(disabled)"
    assert status["configured"] is False
    assert "offline" in status["note"]


def test_provider_status_reports_missing_keys_when_selected_but_incomplete(cfg):
    cfg(AI_PROVIDER="openrouter", AI_MODEL="", AI_API_KEY="")
    status = provider_status()
    assert status["configured"] is False
    assert "MEGATOOL_AI_MODEL" in status["missing"]
    assert "MEGATOOL_AI_API_KEY" in status["missing"]


# --------------------------------------------------------------- determinism guard


def test_get_provider_does_not_require_a_key_for_local_mode(cfg):
    """Local mode must work with no hosted credential present."""
    cfg(AI_PROVIDER="ollama", AI_MODEL="llama3.2", AI_API_KEY="")
    assert is_configured() is True
    p = get_provider()
    assert isinstance(p, OllamaProvider)
