"""Typed application configuration using pydantic-settings."""

import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal, cast
from urllib.parse import urlparse

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[3]


def _normalize_origin_list(raw_items: object) -> list[str]:
    """Validate and strip a runtime list into a typed list of origin strings."""
    if not isinstance(raw_items, list):
        msg = "CORS_ORIGINS must be a list of strings."
        raise ValueError(msg)

    origins: list[str] = []
    for item in cast("list[object]", raw_items):
        if not isinstance(item, str):
            msg = "All CORS_ORIGINS entries must be strings."
            raise ValueError(msg)
        cleaned = item.strip()
        if cleaned:
            origins.append(cleaned)
    return origins


class Settings(BaseSettings):
    """Application settings loaded from environment variables and `.env`."""

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Adrobot API"
    app_version: str = "0.1.0"
    environment: Literal["development", "staging", "production", "test"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://localhost:3000",
            "http://localhost:8080",
        ]
    )

    keitaro_api_url: str = Field(
        default="",
        validation_alias=AliasChoices("KEITARO_API_URL", "KEITARO_BASE_URL"),
    )
    keitaro_api_key: SecretStr = SecretStr("")
    keitaro_timeout_seconds: float = Field(default=45.0, gt=0.0, le=120.0)
    keitaro_default_domain_id: int = Field(default=1813, gt=0)
    keitaro_default_group_id: int = Field(default=10332, gt=0)
    keitaro_default_traffic_source_id: int = Field(default=836, gt=0)
    keitaro_campaign_prefix: str = Field(default="test_bullo_", min_length=1)

    database_url: str = Field(
        default="sqlite+aiosqlite:///./adrobot.db",
        min_length=1,
    )
    db_echo: bool = False

    @field_validator("keitaro_api_url")
    @classmethod
    def validate_keitaro_api_url(cls, value: str) -> str:
        """Normalize and validate the Keitaro base URL when configured."""
        cleaned = value.strip().rstrip("/")
        if not cleaned:
            return ""
        parsed = urlparse(cleaned)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            msg = "KEITARO_API_URL must be a valid HTTP or HTTPS URL."
            raise ValueError(msg)
        return cleaned

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> list[str]:
        """Support JSON arrays or comma-separated origin lists."""
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            if stripped.startswith("["):
                decoded: object = json.loads(stripped)
                return _normalize_origin_list(decoded)
            return [origin.strip() for origin in stripped.split(",") if origin.strip()]
        return _normalize_origin_list(value)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached application settings instance."""
    return Settings()
