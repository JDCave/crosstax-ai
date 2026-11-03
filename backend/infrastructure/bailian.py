"""Minimal Bailian Qwen Chat Completions client using the existing httpx dependency."""

from typing import Any

import httpx

from backend.core.bailian import BailianSettings


class BailianAPIError(Exception):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


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
        if response.is_error:
            # Never expose raw provider bodies: they may contain prompts or credentials.
            reasons = {
                400: "AI_REQUEST_REJECTED",
                401: "AI_AUTHENTICATION_FAILED",
                403: "AI_PERMISSION_DENIED",
                404: "AI_MODEL_OR_ENDPOINT_NOT_FOUND",
                429: "AI_RATE_LIMITED",
            }
            raise BailianAPIError(reasons.get(response.status_code, "AI_PROVIDER_UNAVAILABLE"))
        response.raise_for_status()
        if len(response.content) > 262144:
            raise ValueError("Oversized model response")
        body = response.json()
        if not isinstance(body, dict):
            raise ValueError("Invalid model response")
        return body
