"""LLM provider abstraction: one stable interface, two gateways.

HONEST LABELLING
----------------
Nothing in the quantitative core calls this module. Technical indicators,
scanning, backtesting, portfolio/risk, Fibonacci and transaction-cost
arithmetic are deterministic and independently testable; an LLM must never
invent a price or silently replace a calculation. This module exists so that
*narrative* work (drafting a journal note, summarising a floor sheet) can be
delegated to a model **only** when the owner has explicitly selected a provider.

Two gateways sit behind the same :class:`BaseLLMProvider` interface:

``ollama``
    A local Ollama server (default ``http://localhost:11434``). Optional. The
    application never *requires* it: with no provider configured the factory
    returns :class:`DisabledProvider`, which refuses to run rather than
    silently reaching for localhost.

``openrouter``
    The selected hosted gateway. Requires an API key supplied through the
    environment (``MEGATOOL_AI_API_KEY``), never committed, never logged, and
    never echoed back in an error. Selection is ``MEGATOOL_AI_PROVIDER``.

Safety properties this module guarantees:

* **No request is made** unless a provider is explicitly selected *and* its
  prerequisites (model, and key for the hosted gateway) are present.
* **One attempt per call.** Retrying a timed-out hosted request risks paying
  twice for the same prompt, so failures surface immediately instead.
* **The API key never appears** in an exception message, a result, or a status
  report — only its presence and length are ever reported.
* **Timeouts are bounded** (``MEGATOOL_AI_TIMEOUT``, default 60 s).

Tests inject an ``httpx.MockTransport`` so no test touches the network.
"""

from __future__ import annotations

import abc
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from . import config

# --------------------------------------------------------------------------- errors


class LLMError(Exception):
    """Base class for every provider failure."""


class LLMNotConfigured(LLMError):
    """No provider selected, or a required prerequisite is missing.

    Raised *before* any network attempt, so an unconfigured app can never dial
    out by accident.
    """


class LLMUnavailable(LLMError):
    """The endpoint could not be reached (connection refused / timeout)."""


class LLMRequestError(LLMError):
    """The endpoint answered, but with an error status or unusable payload."""


# --------------------------------------------------------------------------- result


@dataclass(frozen=True)
class LLMResult:
    """A completed generation. Carries no secret material."""

    text: str
    provider: str
    model: str
    usage: dict[str, int] = field(default_factory=dict)
    elapsed_seconds: float = 0.0

    @property
    def prompt_tokens(self) -> int:
        return int(self.usage.get("prompt_tokens", 0))

    @property
    def completion_tokens(self) -> int:
        return int(self.usage.get("completion_tokens", 0))


# --------------------------------------------------------------------------- base


def _redact(text: str, secret: str) -> str:
    """Scrub ``secret`` from ``text`` so it can never be reported."""
    if secret and secret in text:
        return text.replace(secret, "[redacted]")
    return text


class BaseLLMProvider(abc.ABC):
    """Shared plumbing: message building, bounded HTTP, and key redaction."""

    name: str = "base"

    def __init__(
        self,
        model: str,
        *,
        timeout: float | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.model = model
        self.timeout = float(timeout if timeout is not None else config.AI_TIMEOUT_SECONDS)
        self._transport = transport
        #: Subclasses that hold a secret set this so errors can be scrubbed.
        self._secret: str = ""

    # -- helpers ---------------------------------------------------------
    @staticmethod
    def _messages(prompt: str, system: str | None) -> list[dict[str, str]]:
        msgs: list[dict[str, str]] = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.append({"role": "user", "content": prompt})
        return msgs

    def _post_json(
        self,
        url: str,
        *,
        headers: dict[str, str] | None,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """POST once, translating every failure into a typed :class:`LLMError`.

        A single attempt is deliberate: retrying a hosted request that has
        already been accepted (but timed out on the way back) can charge twice.
        """
        try:
            with httpx.Client(timeout=self.timeout, transport=self._transport) as client:
                resp = client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise LLMUnavailable(
                f"{self.name}: request to {url} timed out after {self.timeout:g}s"
            ) from exc
        except httpx.TransportError as exc:
            # Connection refused, DNS failure, TLS error ...
            reason = _redact(str(exc), self._secret)
            raise LLMUnavailable(f"{self.name}: cannot reach {url}: {reason}") from exc

        if resp.status_code >= 400:
            body = _redact(resp.text[:500], self._secret)
            raise LLMRequestError(f"{self.name}: HTTP {resp.status_code} from {url}: {body}")
        try:
            data = resp.json()
        except ValueError as exc:
            raise LLMRequestError(f"{self.name}: response from {url} was not valid JSON") from exc
        if not isinstance(data, dict):
            raise LLMRequestError(f"{self.name}: unexpected JSON shape from {url}")
        return data

    @abc.abstractmethod
    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.0,
    ) -> LLMResult:
        """Run one generation and return the model's text plus usage."""


# --------------------------------------------------------------------------- disabled


class DisabledProvider(BaseLLMProvider):
    """The default when no provider is selected. Never touches the network."""

    name = "disabled"

    def __init__(self) -> None:
        super().__init__(model="")

    def complete(self, prompt, *, system=None, max_tokens=None, temperature=0.0):  # noqa: ANN001
        raise LLMNotConfigured(
            "No AI provider configured. Set MEGATOOL_AI_PROVIDER=ollama (local) "
            "or =openrouter (hosted, plus MEGATOOL_AI_API_KEY and "
            "MEGATOOL_AI_MODEL). The quantitative core works without any LLM."
        )


# --------------------------------------------------------------------------- ollama


class OllamaProvider(BaseLLMProvider):
    """Local Ollama server via ``POST /api/chat``. No API key required."""

    name = "ollama"

    def __init__(
        self,
        model: str,
        *,
        host: str | None = None,
        timeout: float | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        super().__init__(model, timeout=timeout, transport=transport)
        self.host = (host or config.OLLAMA_HOST).rstrip("/")

    def complete(self, prompt, *, system=None, max_tokens=None, temperature=0.0):  # noqa: ANN001
        if not self.model:
            raise LLMNotConfigured(
                "ollama: no model selected. Set MEGATOOL_AI_MODEL (e.g. 'llama3.2')."
            )
        cap = int(max_tokens if max_tokens is not None else config.AI_MAX_TOKENS)
        url = f"{self.host}/api/chat"
        payload = {
            "model": self.model,
            "messages": self._messages(prompt, system),
            "stream": False,
            "options": {"temperature": temperature, "num_predict": cap},
        }
        started = time.monotonic()
        data = self._post_json(url, headers=None, payload=payload)
        elapsed = time.monotonic() - started

        message = data.get("message")
        if not isinstance(message, dict) or not isinstance(message.get("content"), str):
            raise LLMRequestError("ollama: unexpected /api/chat response (no message.content)")
        usage = {
            "prompt_tokens": int(data.get("prompt_eval_count", 0) or 0),
            "completion_tokens": int(data.get("eval_count", 0) or 0),
        }
        return LLMResult(
            text=message["content"],
            provider=self.name,
            model=str(data.get("model") or self.model),
            usage=usage,
            elapsed_seconds=elapsed,
        )


# -------------------------------------------------------------------------- openrouter


class OpenRouterProvider(BaseLLMProvider):
    """Hosted gateway at ``https://openrouter.ai/api/v1/chat/completions``."""

    name = "openrouter"
    DEFAULT_BASE = "https://openrouter.ai/api/v1"

    def __init__(
        self,
        model: str,
        *,
        api_key: str,
        base_url: str | None = None,
        timeout: float | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        super().__init__(model, timeout=timeout, transport=transport)
        self._secret = api_key  # for redaction, never printed
        self.api_key = api_key
        self.base_url = (base_url or config.AI_ENDPOINT or self.DEFAULT_BASE).rstrip("/")

    def complete(self, prompt, *, system=None, max_tokens=None, temperature=0.0):  # noqa: ANN001
        if not self.api_key:
            raise LLMNotConfigured(
                "openrouter: no API key. Set MEGATOOL_AI_API_KEY (kept server-"
                "side; never commit it). No request was made."
            )
        if not self.model:
            raise LLMNotConfigured(
                "openrouter: no model selected. Set MEGATOOL_AI_MODEL (an OpenRouter model id)."
            )
        cap = int(max_tokens if max_tokens is not None else config.AI_MAX_TOKENS)
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-Title": "MegaTool",
        }
        payload = {
            "model": self.model,
            "messages": self._messages(prompt, system),
            "max_tokens": cap,
            "temperature": temperature,
        }
        started = time.monotonic()
        data = self._post_json(url, headers=headers, payload=payload)
        elapsed = time.monotonic() - started

        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise LLMRequestError("openrouter: response contained no choices")
        first = choices[0]
        content = None
        if isinstance(first, dict):
            msg = first.get("message")
            if isinstance(msg, dict) and isinstance(msg.get("content"), str):
                content = msg["content"]
        if content is None:
            raise LLMRequestError("openrouter: response choice had no message.content")

        usage_raw = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        usage = {
            "prompt_tokens": int(usage_raw.get("prompt_tokens", 0) or 0),
            "completion_tokens": int(usage_raw.get("completion_tokens", 0) or 0),
        }
        return LLMResult(
            text=content,
            provider=self.name,
            model=str(data.get("model") or self.model),
            usage=usage,
            elapsed_seconds=elapsed,
        )


# --------------------------------------------------------------------------- factory

_PROVIDERS = ("ollama", "openrouter")


def normalise_provider(provider: str | None = None) -> str:
    """Resolve the provider name from an argument or the environment."""
    raw = config.AI_PROVIDER if provider is None else provider
    return (raw or "").strip().lower()


def is_configured(provider: str | None = None) -> bool:
    """True when a provider is selected *and* its prerequisites are present.

    A selected-but-incomplete configuration still returns False here so callers
    can report "not ready" without raising.
    """
    name = normalise_provider(provider)
    if name == "ollama":
        return bool(config.AI_MODEL)
    if name == "openrouter":
        return bool(config.AI_MODEL and config.AI_API_KEY)
    return False


def get_provider(
    provider: str | None = None,
    *,
    model: str | None = None,
    transport: httpx.BaseTransport | None = None,
) -> BaseLLMProvider:
    """Build the selected provider, or :class:`DisabledProvider`.

    ``provider=""`` (the default) yields the disabled provider — the app never
    reaches for a gateway unless asked. An unrecognised non-empty name raises,
    because a typo should not silently disable AI.
    """
    name = normalise_provider(provider)
    if not name:
        return DisabledProvider()
    if name == "ollama":
        return OllamaProvider(model or config.AI_MODEL, transport=transport)
    if name == "openrouter":
        return OpenRouterProvider(
            model or config.AI_MODEL, api_key=config.AI_API_KEY, transport=transport
        )
    raise LLMNotConfigured(
        f"unknown AI provider {name!r}; expected one of {', '.join(_PROVIDERS)} or '' (disabled)"
    )


def provider_status(provider: str | None = None) -> dict[str, Any]:
    """A redaction-safe description of the current AI configuration.

    Reports only the presence and length of the key — never its value — so it
    is safe to print from a CLI or return from an API.
    """
    name = normalise_provider(provider)
    key = config.AI_API_KEY
    ready = is_configured(name)
    status: dict[str, Any] = {
        "provider": name or "(disabled)",
        "model": config.AI_MODEL or "",
        "endpoint": config.AI_ENDPOINT or (config.OLLAMA_HOST if name == "ollama" else ""),
        "has_api_key": bool(key),
        "api_key_length": len(key),
        "timeout_seconds": config.AI_TIMEOUT_SECONDS,
        "max_tokens_default": config.AI_MAX_TOKENS,
        "configured": ready,
        "selection_env": "MEGATOOL_AI_PROVIDER",
    }
    if not name:
        status["note"] = (
            "No provider selected; the app runs fully offline and the "
            "quantitative core needs no LLM."
        )
    elif not ready:
        missing = []
        if not config.AI_MODEL:
            missing.append("MEGATOOL_AI_MODEL")
        if name == "openrouter" and not key:
            missing.append("MEGATOOL_AI_API_KEY")
        status["missing"] = missing
        status["note"] = f"Selected but not ready; missing {', '.join(missing)}."
    elif name == "openrouter":
        status["note"] = (
            "Hosted gateway selected. Requests incur usage cost; the key stays server-side."
        )
    return status
