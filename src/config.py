"""
Settings.

One source of truth for env-driven config. Read once, share everywhere.
We use pydantic-settings so that the same object validates env vars in prod
and accepts overrides in tests via constructor kwargs.

Two LLM providers are supported and they are swapped purely via env:

    LLM_PROVIDER=openai      -> hits api.openai.com
    LLM_PROVIDER=vllm        -> hits a self-hosted VLLM endpoint

VLLM exposes the OpenAI Chat Completions wire format, so we reuse the
official `openai` SDK and just override `base_url` + the model name. No
second client library to maintain.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


LLMProvider = Literal["openai", "vllm"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- App ---
    app_env: Literal["development", "production", "test"] = "development"
    request_timeout_s: float = 30.0
    # ^ end-to-end pipeline timeout. 30s is generous for a chat agent;
    # p95 target is 6s so anything north of that is already a tail.

    # --- LLM provider switch ---
    llm_provider: LLMProvider = "openai"

    # --- OpenAI ---
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str | None = None  # honoured if set, else SDK default

    # --- VLLM (OpenAI-compatible) ---
    # Defaults point at the cloudflare-tunnel-fronted VLLM the team runs.
    vllm_base_url: str = "https://vllm.corerec.online/v1"
    vllm_model: str = "default"
    # Many self-hosted VLLM deployments dont check the key, but the SDK
    # still wants something non-empty. Keep a placeholder if unset.
    vllm_api_key: str = "EMPTY"

    # --- Sessions ---
    session_ttl_s: int = 60 * 60 * 6  # six hours of memory is plenty for a chat session

    # --- Market data ---
    market_data_cache_ttl_s: int = 60 * 15
    # Prices in a quarter hour bucket are accurate enough for a health check
    # and stop yfinance from rate-limiting us in dev.

    @property
    def active_model(self) -> str:
        return self.vllm_model if self.llm_provider == "vllm" else self.openai_model


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    # tests want a fresh Settings after monkeypatching env
    get_settings.cache_clear()
