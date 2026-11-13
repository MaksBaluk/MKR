"""LLM status for the health endpoint. Keys stay server-side; chat models live in backend.agents.model."""
from __future__ import annotations

from backend.config import get_settings


def status() -> dict:
    settings = get_settings()
    return {"provider": settings.llm_provider, "configured": settings.llm_ready,
            "model": settings.llm_model if settings.llm_ready else None}
