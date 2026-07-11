from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="CWCC_", extra="ignore")

    # --- Service identity ---
    environment: Literal["development", "staging", "production"] = "development"
    service_name: str = "composition-workspace-capability"

    # --- Database ---
    database_url: str = "sqlite:///./composition_workspace.db"
    database_echo: bool = False

    # --- Networking ---
    host: str = "0.0.0.0"
    port: int = 8000
    mount_prefix: str = ""

    # --- Logging ---
    log_level: str = "INFO"
    log_format: Literal["json", "plain"] = "json"

    # --- TANTRA integration ---
    tantra_runtime_version: str = "1.0.0"
    host_name: str = "standalone"

    # --- Adapter toggles (all default on; can be disabled per-environment) ---
    enable_bucket_adapter: bool = True
    enable_replay_adapter: bool = True
    enable_insightflow_adapter: bool = True
    enable_runtime_registry_adapter: bool = True
    enable_rajya_adapter: bool = True

    # --- Startup validation ---
    fail_fast_on_startup_errors: bool = True

    @field_validator("port")
    @classmethod
    def _port_in_valid_range(cls, v: int) -> int:
        if not (1 <= v <= 65535):
            raise ValueError(f"port must be between 1 and 65535, got {v}")
        return v

    @field_validator("database_url")
    @classmethod
    def _database_url_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("database_url must not be blank")
        return v

    @field_validator("log_level")
    @classmethod
    def _log_level_is_known(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in valid:
            raise ValueError(f"log_level must be one of {sorted(valid)}, got '{v}'")
        return v.upper()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
