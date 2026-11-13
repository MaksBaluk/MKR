"""LLM status and HTTP transport for Interviewer/Evaluator roles. Keys stay server-side."""
from __future__ import annotations

import http.client
import json
import urllib.error
import urllib.request

from backend.config import get_settings
from backend.providers.roles import LLMError


def status() -> dict:
    settings = get_settings()
    return {"provider": settings.llm_provider, "configured": settings.llm_ready,
            "model": settings.llm_model if settings.llm_ready else None}


class HttpTransport:
    """Minimal Anthropic / OpenAI-compatible chat transport. Maps failures to LLMError kinds."""

    def __init__(self, provider: str, api_key: str, model: str, base_url: str):
        self.provider, self.api_key, self.model, self.base_url = provider, api_key, model, base_url

    def complete(self, system: str, user: str, *, timeout_s: float) -> str:
        if self.provider == "anthropic":
            url = "https://api.anthropic.com/v1/messages"
            headers = {"x-api-key": self.api_key, "anthropic-version": "2023-06-01",
                       "content-type": "application/json"}
            body = {"model": self.model, "max_tokens": 900, "system": system,
                    "messages": [{"role": "user", "content": user}]}
        else:
            url = self.base_url.rstrip("/") + "/chat/completions"
            headers = {"Authorization": f"Bearer {self.api_key}", "content-type": "application/json"}
            body = {"model": self.model, "max_tokens": 1500,
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:  # noqa: S310 - fixed https endpoints
                data = json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            raise LLMError("RATE_LIMIT" if exc.code == 429 else "OFFLINE") from exc
        except TimeoutError as exc:
            raise LLMError("TIMEOUT") from exc
        except (urllib.error.URLError, OSError, http.client.HTTPException) as exc:
            raise LLMError("OFFLINE") from exc  # includes dropped/incomplete reads
        except ValueError as exc:
            raise LLMError("MALFORMED") from exc  # non-JSON envelope
        try:
            if self.provider == "anthropic":
                return "".join(part.get("text", "") for part in data.get("content", []))
            return data["choices"][0]["message"].get("content") or ""
        except (KeyError, IndexError, TypeError, AttributeError) as exc:
            raise LLMError("MALFORMED") from exc


def get_transport():
    """Return a configured transport, or None when no provider is configured."""
    settings = get_settings()
    if not settings.llm_ready:
        return None
    return HttpTransport(settings.llm_provider, settings.llm_api_key, settings.llm_model, settings.llm_base_url)
