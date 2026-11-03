"""Per-request counters; usage is reported tokens, never a billing estimate."""

from typing import Any

from pydantic import BaseModel, Field


class AICallMetrics(BaseModel):
    attempts: int = Field(default=0, ge=0)
    retries: int = Field(default=0, ge=0)
    provider_duration_ms: int = Field(default=0, ge=0)
    queue_duration_ms: int = Field(default=0, ge=0)
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    usage_complete: bool = True

    def record_usage(self, body: dict[str, Any]) -> None:
        usage = body.get("usage")
        if not isinstance(usage, dict):
            self.usage_complete = False
            return
        values: list[int | None] = []
        for name in ("prompt_tokens", "completion_tokens", "total_tokens"):
            value = usage.get(name)
            if type(value) is not int or not 0 <= value <= 1_000_000_000:
                self.usage_complete = False
                values.append(None)
                continue
            setattr(self, name, getattr(self, name) + value)
            values.append(value)
        prompt, completion, total = values
        if prompt is not None and completion is not None and total is not None and prompt + completion != total:
            self.usage_complete = False
