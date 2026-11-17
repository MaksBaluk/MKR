import json
from types import SimpleNamespace

import httpx
import pytest
from langchain_core.messages import HumanMessage, SystemMessage

from backend.agents.anthropic_chat import AnthropicChat


def make(handler, **kw):
    return AnthropicChat(api_key="sk-ant-test", model="claude-haiku-5-5", timeout=5, transport=httpx.MockTransport(handler), **kw)


def test_sends_a_messages_api_request_and_returns_the_text():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"], seen["headers"], seen["body"] = str(request.url), request.headers, json.loads(request.content)
        return httpx.Response(200, json={"content": [{"type": "text", "text": "Питання?"}], "stop_reason": "end_turn",
                                         "model": "claude-haiku-5-5-served"})

    out = make(handler).invoke([SystemMessage("Ти інтерв'юер"), HumanMessage("Тема: FastAPI")])
    assert out.content == "Питання?"
    assert out.response_metadata == {"model": "claude-haiku-5-5-served"}  # served model for experiment records
    assert seen["url"] == "https://api.anthropic.com/v1/messages"
    assert seen["headers"]["x-api-key"] == "sk-ant-test" and seen["headers"]["anthropic-version"] == "2023-06-01"
    body = seen["body"]
    assert body["model"] == "claude-haiku-5-5" and body["system"] == "Ти інтерв'юер"
    assert body["messages"] == [{"role": "user", "content": "Тема: FastAPI"}] and body["max_tokens"] > 0


def test_joins_several_text_blocks():
    def handler(request):
        return httpx.Response(200, json={"content": [{"type": "text", "text": "Один "}, {"type": "text", "text": "два"}]})
    assert make(handler).invoke([HumanMessage("x")]).content == "Один два"


def test_rate_limit_is_reported_with_a_rate_limit_error_name():
    def handler(request):
        return httpx.Response(429, json={"error": {"type": "rate_limit_error", "message": "slow down"}})
    with pytest.raises(Exception) as info:
        make(handler).invoke([HumanMessage("x")])
    assert "RateLimit" in type(info.value).__name__


def test_other_errors_do_not_look_like_rate_limits_and_hide_the_key():
    def handler(request):
        return httpx.Response(500, json={"error": {"type": "api_error", "message": "boom"}})
    with pytest.raises(Exception) as info:
        make(handler).invoke([HumanMessage("x")])
    assert "RateLimit" not in type(info.value).__name__ and "sk-ant-test" not in str(info.value)


def test_get_chat_model_builds_the_anthropic_client(monkeypatch):
    from backend.agents import model as model_mod
    settings = SimpleNamespace(llm_ready=True, llm_provider="anthropic", llm_api_key="sk-ant-x", llm_model="claude-haiku-5-5",
                               llm_base_url="", llm_timeout_seconds=30.0)
    monkeypatch.setattr(model_mod, "get_settings", lambda: settings)
    assert isinstance(model_mod.get_chat_model(), AnthropicChat)
