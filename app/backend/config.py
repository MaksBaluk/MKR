"""Environment-driven configuration. Credentials never sent to the browser."""
from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ROOT / ".env"), extra="ignore")

    database_url: str = "sqlite+pysqlite:///./local-demo.db"
    app_name: str = "CompetenceMatch"
    app_env: str = "development"
    demo_mode: bool = False
    demo_email: str = "demo@competencematch.local"
    demo_password: str = ""
    frontend_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    llm_provider: str = "disabled"  # disabled | anthropic | openai_compatible
    llm_api_key: str = ""
    llm_model: str = "claude-sonnet-4-5"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_timeout_seconds: float = 18.0
    llm_question_rephrasing: bool = False
    llm_question_generation: bool = True
    llm_question_strategy: str = "hybrid"  # hybrid: bank MCQ + generated follow-up; dynamic: all generated

    @property
    def llm_ready(self) -> bool:
        return self.llm_provider in ("anthropic", "openai_compatible") and bool(self.llm_api_key) and bool(self.llm_model)


@lru_cache
def get_settings() -> Settings:
    return Settings()
