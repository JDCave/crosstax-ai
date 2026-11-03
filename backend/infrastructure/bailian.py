"""Minimal Bailian Qwen Chat Completions client using the existing httpx dependency."""

from typing import Any

import httpx

from backend.core.ai_errors import REASON_CODES, AIErrorCategory, AIErrorInfo
from backend.core.bailian import BailianSettings


class BailianAPIError(Exception):
    def __init__(self, category: AIErrorCategory, status: int, provider_code: str | None) -> None:
        self.reason_code = REASON_CODES[category]
        super().__init__(self.reason_code)
        self.error = AIErrorInfo.for_category(category)
        self.provider_status = status
        self.provider_code = provider_code


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
    return BailianAPIError(category, status, provider_code)


class BailianClient:
    def __init__(self, settings: BailianSettings, client: httpx.AsyncClient) -> None:
        self.settings = settings
        self.client = client

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
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
        response = await self.client.post(
            self.settings.base_url + "/chat/completions",
            headers={"Authorization": "Bearer " + self.settings.effective_api_key()},
            json=payload,
        )
        if not response.is_success:
            raise classify_bailian_error(response)
        response.raise_for_status()
        if len(response.content) > 262144:
            raise ValueError("Oversized model response")
        body = response.json()
        if not isinstance(body, dict):
            raise ValueError("Invalid model response")
        return body
