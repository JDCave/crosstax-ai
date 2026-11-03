"""Minimal Bailian Qwen Chat Completions client using the existing httpx dependency."""

import asyncio
import random
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from backend.core.ai_errors import REASON_CODES, AIErrorCategory, AIErrorInfo
from backend.core.ai_metrics import AICallMetrics
from backend.core.bailian import BailianSettings


class BailianAPIError(Exception):
    def __init__(
        self,
        category: AIErrorCategory,
        status: int,
        provider_code: str | None,
        retry_after_seconds: float | None = None,
    ) -> None:
        self.reason_code = REASON_CODES[category]
        super().__init__(self.reason_code)
        self.error = AIErrorInfo.for_category(category)
        self.provider_status = status
        self.provider_code = provider_code
        self.retry_after_seconds = retry_after_seconds


def classify_bailian_error(response: httpx.Response) -> BailianAPIError:
    # Exact allowlist only. Never log arbitrary supplier codes or error messages.
    codes = {
        "InvalidApiKey": AIErrorCategory.AUTHENTICATION,
        "invalid_api_key": AIErrorCategory.AUTHENTICATION,
        "AccessDenied": AIErrorCategory.PERMISSION,
        "access_denied": AIErrorCategory.PERMISSION,
        "Model.AccessDenied": AIErrorCategory.PERMISSION,
        "Arrearage": AIErrorCategory.QUOTA,
        "insufficient_quota": AIErrorCategory.QUOTA,
        "BudgetLimitExceeded": AIErrorCategory.QUOTA,
        "PrepaidBillOverdue": AIErrorCategory.QUOTA,
        "PostpaidBillOverdue": AIErrorCategory.QUOTA,
        "Throttling.RateQuota": AIErrorCategory.RATE_LIMIT,
        "Throttling.AllocationQuota": AIErrorCategory.RATE_LIMIT,
        "Throttling.BurstRate": AIErrorCategory.RATE_LIMIT,
        "Throttling.ServiceOverloaded": AIErrorCategory.SERVICE_UNAVAILABLE,
        "Throttling.ResourceExhausted": AIErrorCategory.SERVICE_UNAVAILABLE,
        "ModelNotFound": AIErrorCategory.INVALID_REQUEST,
        "NotFound": AIErrorCategory.INVALID_REQUEST,
        "InvalidParameter": AIErrorCategory.INVALID_REQUEST,
    }
    provider_code = None
    try:
        body = response.json() if len(response.content) <= 262144 else {}
        error = body.get("error", body)
        code = error.get("code") or error.get("type")
        if isinstance(code, str) and code in codes:
            provider_code = code
    except (ValueError, AttributeError, TypeError):
        pass
    status = response.status_code
    if status in (408, 504):
        category = AIErrorCategory.TIMEOUT
    elif status >= 500:
        category = AIErrorCategory.SERVICE_UNAVAILABLE
    elif status == 401:
        category = AIErrorCategory.AUTHENTICATION
    elif provider_code is not None:
        category = codes[provider_code]
    elif status == 403:
        category = AIErrorCategory.PERMISSION
    elif status == 429:
        category = AIErrorCategory.RATE_LIMIT
    else:
        category = AIErrorCategory.INVALID_REQUEST
    return BailianAPIError(category, status, provider_code, parse_retry_after(response.headers.get("Retry-After")))


def parse_retry_after(value: str | None) -> float | None:
    """Accept delta-seconds or an HTTP-date; never shorten the provider's requested delay."""
    if value is None:
        return None
    try:
        if value.strip().isdigit():
            return float(int(value.strip())) if len(value.strip()) <= 8 else float("inf")
        date = parsedate_to_datetime(value)
        if date.tzinfo is None:
            return None
        return max(0.0, (date - datetime.now(UTC)).total_seconds())
    except (ValueError, TypeError, OverflowError):
        return None


class BailianClient:
    def __init__(
        self,
        settings: BailianSettings,
        client: httpx.AsyncClient,
        metrics: AICallMetrics | None = None,
        deadline: float | None = None,
    ) -> None:
        self.settings = settings
        self.client = client
        self.metrics = metrics if metrics is not None else AICallMetrics()
        self.deadline = deadline if deadline is not None else time.monotonic() + settings.timeout_seconds
        self.retries_used = 0  # Shared across every tool/final round in one agent invocation.

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        async with asyncio.timeout(max(0, self.deadline - time.monotonic())):
            return await self._complete(messages, tools)

    async def _complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.settings.model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": 2500,
            "stream": False,
            "enable_thinking": False,
        }
        if tools:
            payload.update(tools=tools, tool_choice="auto", parallel_tool_calls=True)
        else:
            payload["response_format"] = {"type": "json_object"}
        while True:
            response = await self._request(payload)
            if response.is_success:
                try:
                    body = response.json()
                except ValueError:
                    self.metrics.usage_complete = False
                    raise
                if not isinstance(body, dict):
                    self.metrics.usage_complete = False
                    raise ValueError("Invalid model response")
                self.metrics.record_usage(body)
                return body
            self.metrics.usage_complete = False
            error = classify_bailian_error(response)
            # Retry only explicit rate/server rejections. A read timeout or disconnect
            # after sending may already have incurred tokens, so never replay it automatically.
            if (
                response.status_code not in (429, 500, 502, 503)
                or not error.error.retryable
                or self.retries_used >= self.settings.max_retries
            ):
                raise error
            delay = error.retry_after_seconds
            if delay is None:
                delay = random.uniform(0.15, 0.3) * (2**self.retries_used)
            if delay + 0.05 >= self.deadline - time.monotonic():
                raise error  # Do not sleep past the budget or shorten Retry-After.
            await asyncio.sleep(delay)
            self.retries_used += 1
            self.metrics.retries += 1

    async def _request(self, payload: dict[str, Any]) -> httpx.Response:
        self.metrics.attempts += 1
        started = time.monotonic()
        try:
            async with self.client.stream(
                "POST",
                self.settings.base_url + "/chat/completions",
                headers={"Authorization": "Bearer " + self.settings.effective_api_key()},
                json=payload,
                timeout=max(0.001, self.deadline - time.monotonic()),
            ) as response:
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(content) + len(chunk) > 262144:
                        raise ValueError("Oversized model response")
                    content.extend(chunk)
                return httpx.Response(
                    response.status_code,
                    headers={
                        key: value
                        for key, value in response.headers.items()
                        if key not in {"content-encoding", "content-length", "transfer-encoding"}
                    },
                    content=bytes(content),
                    request=response.request,
                )
        except BaseException:
            self.metrics.usage_complete = False
            raise  # Preserve cancellation as well as failures.
        finally:
            self.metrics.provider_duration_ms += int((time.monotonic() - started) * 1000)
