"""Application configuration via pydantic-settings."""

from __future__ import annotations

import functools
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """Database connection configuration."""

    model_config = SettingsConfigDict(env_prefix="DATABASE_")

    url: str = Field(
        default="sqlite+aiosqlite:///./crosstax.db",
        description="SQLAlchemy async connection URL",
    )
    pool_size: int = Field(default=5, ge=1)
    max_overflow: int = Field(default=10, ge=0)
    pool_recycle: int = Field(default=1800, description="Recycle connections after N seconds")
    pool_pre_ping: bool = Field(default=True, description="Enable connection health check before use")
    echo: bool = Field(default=False, description="Log all SQL statements")


class RedisSettings(BaseSettings):
    """Redis connection configuration."""

    model_config = SettingsConfigDict(env_prefix="REDIS_")

    url: str = Field(default="redis://localhost:6379/0")
    max_connections: int = Field(default=10, ge=1)


class Settings(BaseSettings):
    """Root application settings loaded from environment and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    environment: Literal["dev", "test", "prod"] = Field(default="dev")
    debug: bool = Field(default=False)
    log_level: str = Field(default="INFO")
    log_format: Literal["json", "console"] = Field(default="json")
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)

    cors_origins: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:5173"],
        description="Allowed CORS origins",
    )

    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings singleton."""
    return Settings()
