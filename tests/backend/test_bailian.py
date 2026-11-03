"""Bailian configuration and wire protocol without a real API key or paid calls."""

import json

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from backend.core.bailian import BailianSettings
from backend.infrastructure.bailian import BailianAPIError, BailianClient


@pytest.fixture(autouse=True)
def isolated_keys(monkeypatch):
    monkeypatch.delenv("RULE_AI_API_KEY", raising=False)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)


def test_key_only_configuration_and_standard_dashscope_key(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "standard-key")
    settings = BailianSettings(_env_file=None)
    assert settings.model == "qwen-plus"
    assert settings.enabled
    assert settings.effective_api_key() == "standard-key"
    monkeypatch.setenv("RULE_AI_API_KEY", "engine-key")
    assert BailianSettings(_env_file=None).effective_api_key() == "engine-key"
    monkeypatch.setenv("RULE_AI_API_KEY", "")
    assert BailianSettings(_env_file=None).effective_api_key() == "standard-key"
    assert "standard-key" not in repr(settings)


def test_empty_dotenv_placeholder_does_not_mask_environment_key(tmp_path, monkeypatch):
    config = tmp_path / ".env"
    config.write_text("RULE_AI_API_KEY=\nRULE_AI_MODEL=\n")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "environment-key")
    settings = BailianSettings(_env_file=config)
    assert settings.effective_api_key() == "environment-key"
    assert settings.model == "qwen-plus"


@pytest.mark.parametrize(
    "url",
    [
        "http://dashscope.aliyuncs.com/compatible-mode/v1",
        "https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
        "https://key:secret@example.com/v1",
        "https://example.com/v1?key=secret",
        "https://example.com/v1#fragment",
        "https://example.com/v1/chat/completions",
    ],
)
def test_invalid_or_placeholder_endpoints_are_rejected(url):
    with pytest.raises(ValidationError):
        BailianSettings(base_url=url, _env_file=None)


async def test_bailian_tool_and_json_stages_send_valid_distinct_parameters():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    settings = BailianSettings(api_key=SecretStr("local-test-key"), _env_file=None)
    tools = [{"type": "function", "function": {"name": "read", "parameters": {"type": "object"}}}]
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = BailianClient(settings, client)
        messages = [{"role": "system", "content": "Return JSON."}]
        await provider.complete(messages, tools)
        await provider.complete(messages)
    assert all(
        str(request.url) == "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions" for request in requests
    )
    assert all(request.headers["Authorization"] == "Bearer local-test-key" for request in requests)
    first, last = [json.loads(request.content) for request in requests]
    assert first["tools"] == tools and first["tool_choice"] == "auto"
    assert first["parallel_tool_calls"] is True
    assert "response_format" not in first
    assert last["response_format"] == {"type": "json_object"}
    assert "tools" not in last
    assert all(body["enable_thinking"] is False and body["stream"] is False for body in (first, last))


@pytest.mark.parametrize(
    "status,reason",
    [
        (400, "AI_REQUEST_REJECTED"),
        (401, "AI_AUTHENTICATION_FAILED"),
        (403, "AI_PERMISSION_DENIED"),
        (404, "AI_MODEL_OR_ENDPOINT_NOT_FOUND"),
        (429, "AI_RATE_LIMITED"),
        (503, "AI_PROVIDER_UNAVAILABLE"),
    ],
)
async def test_provider_failures_are_classified_without_returning_raw_body(status, reason):
    settings = BailianSettings(api_key=SecretStr("local-test-key"), _env_file=None)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(status, json={"message": "PRIVATE RESPONSE"}),
        )
    ) as client:
        with pytest.raises(BailianAPIError) as caught:
            await BailianClient(settings, client).complete([])
    assert caught.value.reason_code == reason
    assert "PRIVATE RESPONSE" not in str(caught.value)


async def test_workspace_endpoint_is_respected():
    url = "https://demo-workspace.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1/"
    settings = BailianSettings(base_url=url, _env_file=None)
    received = []

    def handler(request):
        received.append(str(request.url))
        return httpx.Response(200, json={})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await BailianClient(settings, client).complete([])
    assert received == [url.rstrip("/") + "/chat/completions"]
