"""Service configuration via environment (pydantic-settings).

Fail-fast: if a required secret is missing the service refuses to start with a clear
error, rather than booting and failing on the first request. Load once at startup and
inject via DI.
"""
from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Service auth (the website's backend holds this; never exposed to browser JS).
    service_api_key: str = Field(min_length=8)

    # Primary provider: 9Router.
    ninerouter_url: str
    ninerouter_key: str

    # Failover provider: OpenAI direct. Optional — if unset, failover is disabled and
    # a primary outage surfaces as a 503 instead of silently switching.
    openai_api_key: str = ""
    openai_failover_model: str = "gpt-4o"

    # Generation params (validated demo defaults).
    default_model: str = "sonnet-4.5"
    temperature: float = 0.2
    max_tokens: int = 1500

    # Limits / request hardening.
    max_history_msgs: int = 40
    max_message_chars: int = 8000
    rate_limit_per_min: int = 30
    ttft_timeout_s: float = 15.0
    read_timeout_s: float = 120.0

    # Circuit breaker.
    breaker_threshold: int = 5
    breaker_cooldown_s: float = 60.0

    @property
    def failover_enabled(self) -> bool:
        return bool(self.openai_api_key)
