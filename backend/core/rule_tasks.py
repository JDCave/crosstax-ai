"""Environment-only task configuration and standard authenticated encryption."""

import base64
import hashlib
import hmac
import json
from typing import Any

from cryptography.fernet import Fernet, MultiFernet
from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class RuleTaskSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RULE_TASK_", env_file=".env", extra="ignore")
    encryption_keys: list[SecretStr] = Field(default_factory=list)
    capacity: int = Field(default=100, ge=1, le=10000)
    timeout_seconds: float = Field(default=30, ge=1, le=30)
    retention_seconds: int = Field(default=86400, ge=60, le=604800)
    lease_seconds: float = Field(default=5, ge=2, le=30)
    heartbeat_seconds: float = Field(default=1, ge=0.1, le=10)
    max_attempts: int = Field(default=3, ge=1, le=10)

    @model_validator(mode="after")
    def validate_lease(self) -> "RuleTaskSettings":
        if self.heartbeat_seconds >= self.lease_seconds / 2:
            raise ValueError("Heartbeat must be shorter than half the lease")
        return self


class TaskCipher:
    def __init__(self, keys: list[SecretStr]) -> None:
        if not keys:
            raise ValueError("Task encryption is not configured")
        self._keys = [key.get_secret_value().encode("ascii") for key in keys]
        self._cipher = MultiFernet([Fernet(key) for key in self._keys])

    @staticmethod
    def canonical(value: Any) -> bytes:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()

    def encrypt(self, value: Any) -> str:
        return self._cipher.encrypt(self.canonical(value)).decode("ascii")

    def decrypt(self, value: str) -> Any:
        return json.loads(self._cipher.decrypt(value.encode("ascii")))

    def digests(self, value: Any) -> list[str]:
        data = b"crosstax-task-request-v1\x00" + self.canonical(value)
        return [hmac.new(base64.urlsafe_b64decode(key), data, hashlib.sha256).hexdigest() for key in self._keys]

    def encrypt_pdf(self, value: bytes) -> str:
        return self._cipher.encrypt(b"crosstax-pdf-v1\x00" + value).decode("ascii")

    def decrypt_pdf(self, value: str) -> bytes:
        data = self._cipher.decrypt(value.encode("ascii"))
        prefix = b"crosstax-pdf-v1\x00"
        if not data.startswith(prefix):
            raise ValueError("Invalid report encryption domain")
        return data[len(prefix) :]
