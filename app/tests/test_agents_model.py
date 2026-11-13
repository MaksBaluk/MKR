from backend.agents.model import get_chat_model
from backend.config import get_settings


def _with_env(monkeypatch, **env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()


def test_none_when_disabled(monkeypatch):
    _with_env(monkeypatch, LLM_PROVIDER="disabled")
    try:
        assert get_chat_model() is None
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


def test_chat_openai_with_configured_base_url(monkeypatch):
    from langchain_openai import ChatOpenAI

    _with_env(
        monkeypatch,
        LLM_PROVIDER="openai_compatible",
        LLM_API_KEY="test-key",
        LLM_MODEL="test-model",
        LLM_BASE_URL="https://example.test/v1",
    )
    try:
        model = get_chat_model()
        assert isinstance(model, ChatOpenAI)
        assert model.openai_api_base == "https://example.test/v1"
        assert model.model_name == "test-model"
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()
