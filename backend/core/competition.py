"""Opt-in competition demonstration and internal initialization controls."""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class DemoSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RULE_DEMO_", env_file=".env", extra="ignore")
    enabled: bool = False


class SetupSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RULE_SETUP_", env_file=".env", extra="ignore")
    enabled: bool = False
    token: SecretStr = SecretStr("")


@lru_cache(maxsize=1)
def get_demo_settings() -> DemoSettings:
    return DemoSettings()


@lru_cache(maxsize=1)
def get_setup_settings() -> SetupSettings:
    return SetupSettings()
