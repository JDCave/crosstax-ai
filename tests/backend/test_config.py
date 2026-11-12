"""Tests for application configuration."""

from __future__ import annotations

import pytest

from backend.core.config import Settings


def test_default_settings(monkeypatch: pytest.MonkeyPatch, tmp_path):
    # Isolate from the developer's local .env and shell env so this tests
    # code defaults only (nested DatabaseSettings reads .env independently).
    monkeypatch.chdir(tmp_path)
    for var in ("ENVIRONMENT", "DEBUG", "PORT", "DATABASE_POOL_SIZE", "DATABASE_MAX_OVERFLOW"):
        monkeypatch.delenv(var, raising=False)

    settings = Settings()
    assert settings.environment == "dev"
    assert settings.debug is False
    assert settings.port == 8000
    assert settings.database.pool_size == 3
    assert settings.database.max_overflow == 0


def test_settings_env_override(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("PORT", "9000")
    monkeypatch.setenv("DATABASE_POOL_SIZE", "10")

    settings = Settings()
    assert settings.environment == "test"
    assert settings.port == 9000
    assert settings.database.pool_size == 10
