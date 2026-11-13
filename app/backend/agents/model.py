from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

from backend.config import get_settings


def get_chat_model() -> BaseChatModel | None:
    """Chat model for the agents, or None when the LLM is not configured.

    OpenAI-compatible endpoints only (e.g. OpenRouter); provider "anthropic" returns None for now.
    """
    s = get_settings()
    if not s.llm_ready or s.llm_provider != "openai_compatible":
        return None
    return ChatOpenAI(
        model=s.llm_model,
        api_key=s.llm_api_key,
        base_url=s.llm_base_url,
        timeout=s.llm_timeout_seconds,
        temperature=0.3,
        max_retries=0,
    )
