"""Minimal Anthropic Messages API client with the same `invoke(messages)` shape the agents already use.

No new dependency: plain httpx. Errors never include the key or the prompt; HTTP 429 raises a RateLimit-named error so
the agents' rate-limit retry applies to this provider too.
"""
from __future__ import annotations

from types import SimpleNamespace

import httpx

ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_BASE_URL = "https://api.anthropic.com/v1"


class AnthropicAPIError(RuntimeError):
    pass


class AnthropicRateLimitError(AnthropicAPIError):
    pass


class AnthropicChat:
    def __init__(self, *, api_key: str, model: str, timeout: float = 120.0, base_url: str = DEFAULT_BASE_URL,
                 max_tokens: int = 1500, temperature: float = 0.3, transport: httpx.BaseTransport | None = None):
        self._api_key, self._model = api_key, model
        self._base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self._max_tokens, self._temperature = max_tokens, temperature
        self._client = httpx.Client(timeout=timeout, transport=transport)

    def invoke(self, messages, *args, **kwargs):
        system = "\n\n".join(str(m.content) for m in messages if getattr(m, "type", "") == "system")
        turns = [{"role": "assistant" if getattr(m, "type", "") == "ai" else "user", "content": str(m.content)}
                 for m in messages if getattr(m, "type", "") != "system"]
        body = {"model": self._model, "max_tokens": self._max_tokens, "temperature": self._temperature, "messages": turns}
        if system:
            body["system"] = system
        try:
            resp = self._client.post(f"{self._base_url}/messages", json=body, headers={
                "x-api-key": self._api_key, "anthropic-version": ANTHROPIC_VERSION, "content-type": "application/json"})
        except httpx.HTTPError as exc:
            raise AnthropicAPIError(f"network error: {type(exc).__name__}") from None
        if resp.status_code == 429:
            raise AnthropicRateLimitError("rate limited (429)")
        if resp.status_code >= 400:
            raise AnthropicAPIError(f"HTTP {resp.status_code}")
        data = resp.json()
        text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        return SimpleNamespace(content=text, response_metadata={"model": data.get("model")})
