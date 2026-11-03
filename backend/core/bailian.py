"""Bailian configuration; requests remain opt-in via include_guidance."""

from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class BailianSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RULE_AI_", env_file=".env", extra="ignore")
    enabled: bool = True
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    api_key: SecretStr = SecretStr("")
    dashscope_api_key: SecretStr = Field(default=SecretStr(""), validation_alias="DASHSCOPE_API_KEY")
    model: str = "qwen-plus"
    timeout_seconds: float = Field(default=8.0, gt=0, le=20)
    max_concurrency: int = Field(default=2, ge=1, le=5)

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or "{" in value
            or "}" in value
            or parsed.path.endswith("/chat/completions")
        ):
            raise ValueError("Use a complete HTTPS compatible-mode base URL without credentials or placeholders")
        return value

    @field_validator("model")
    @classmethod
    def default_model(cls, value: str) -> str:
        return value.strip() or "qwen-plus"

    def effective_api_key(self) -> str:
        """A populated engine-specific key wins; empty placeholders do not mask DashScope's standard key."""
        return self.api_key.get_secret_value().strip() or self.dashscope_api_key.get_secret_value().strip()
