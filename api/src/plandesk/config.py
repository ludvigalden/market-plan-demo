"""Runtime configuration read from the environment."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://plandesk@127.0.0.1:55432/plandesk"

    holidays_base_url: str = "https://date.nager.at"
    holidays_timeout_seconds: float = 5.0
    holidays_max_attempts: int = 3
    holidays_backoff_seconds: float = 0.3

    ai_provider: Literal["stub", "foundry"] = "stub"
    foundry_project_endpoint: str = ""
    foundry_model_deployment: str = ""

    static_dir: str = ""
    demo_user: str = "demo.planner"


@lru_cache
def get_settings() -> Settings:
    return Settings()
