"""Report worker budgets independent of rule-validation deadlines."""

from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class RuleReportSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RULE_REPORT_", env_file=".env", extra="ignore")
    timeout_seconds: float = Field(default=15, ge=0.1, le=60)
    lease_seconds: float = Field(default=20, ge=2, le=120)
    heartbeat_seconds: float = Field(default=3, ge=0.05, le=30)
    max_attempts: int = Field(default=3, ge=1, le=10)

    @model_validator(mode="after")
    def check_heartbeat(self) -> "RuleReportSettings":
        if self.heartbeat_seconds >= self.lease_seconds / 2:
            raise ValueError("Report heartbeat must be shorter than half the lease")
        return self


@lru_cache(maxsize=1)
def get_report_settings() -> RuleReportSettings:
    return RuleReportSettings()
