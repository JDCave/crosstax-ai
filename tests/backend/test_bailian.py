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
        (404, "AI_REQUEST_REJECTED"),
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


@pytest.mark.parametrize(
    "status,body,category,retryable",
    [
        (401, {"error": {"code": "InvalidApiKey"}}, "authentication", False),
        (403, {"code": "Arrearage"}, "quota", False),
        (429, {"error": {"code": "insufficient_quota"}}, "quota", False),
        (429, {"error": {"code": "Throttling.RateQuota"}}, "rate_limit", True),
        (429, {"error": {"code": "Throttling.AllocationQuota"}}, "rate_limit", True),
        (400, {"error": {"code": "BudgetLimitExceeded"}}, "quota", False),
        (403, {"error": {"code": "AccessDenied"}}, "permission", False),
        (404, {"error": {"code": "ModelNotFound"}}, "invalid_request", False),
        (422, {}, "invalid_request", False),
        (408, {}, "timeout", True),
        (504, {}, "timeout", True),
        (503, {"error": {"code": "InvalidParameter"}}, "service_unavailable", True),
        (429, {"error": {"code": "PRIVATE SUPPLIER VALUE"}}, "rate_limit", True),
    ],
)
def test_normalized_error_categories_and_retry_policy(status, body, category, retryable):
    from backend.infrastructure.bailian import classify_bailian_error

    error = classify_bailian_error(httpx.Response(status, json=body))
    assert error.error.category == category
    assert error.error.retryable is retryable
    assert error.provider_status == status
    assert "PRIVATE" not in str(error) and "PRIVATE" not in str(error.provider_code)


def test_model_is_overridable_through_environment(monkeypatch):
    monkeypatch.setenv("RULE_AI_MODEL", "deployment-model-version")
    assert BailianSettings(_env_file=None).model == "deployment-model-version"


async def test_bounded_retry_recovers_and_reports_known_usage():
    from backend.core.ai_metrics import AICallMetrics

    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, json={"usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}})

    metrics = AICallMetrics()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await BailianClient(BailianSettings(_env_file=None), client, metrics).complete([])
    assert len(calls) == 2 and calls[0] == calls[1]
    assert metrics.attempts == 2 and metrics.retries == 1
    assert metrics.total_tokens == 12
    assert not metrics.usage_complete  # Failed attempts may not report token usage.


async def test_retry_budget_is_shared_across_model_rounds():
    replies = [429, 200, 503]
    calls = []

    def handler(request):
        status = replies[len(calls)]
        calls.append(request)
        return httpx.Response(status, headers={"Retry-After": "0"}, json={})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = BailianClient(BailianSettings(_env_file=None, max_retries=1), client)
        await provider.complete([])
        with pytest.raises(BailianAPIError):
            await provider.complete([])
    assert len(calls) == 3 and provider.metrics.retries == 1


@pytest.mark.parametrize(
    "status,body", [(401, {}), (403, {}), (400, {}), (504, {}), (429, {"error": {"code": "insufficient_quota"}})]
)
async def test_permanent_or_execution_unknown_errors_are_not_retried(status, body):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, json=body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = BailianClient(BailianSettings(_env_file=None), client)
        with pytest.raises(BailianAPIError):
            await provider.complete([])
    assert len(calls) == 1 and provider.metrics.retries == 0


async def test_retry_after_exceeding_budget_does_not_wait_or_retry():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": "60"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = BailianClient(BailianSettings(_env_file=None, timeout_seconds=0.1), client)
        with pytest.raises(BailianAPIError):
            await provider.complete([])
    assert len(calls) == 1 and provider.metrics.retries == 0


def test_retry_after_http_date_and_invalid_values():
    from datetime import UTC, datetime, timedelta
    from email.utils import format_datetime

    from backend.infrastructure.bailian import parse_retry_after

    assert parse_retry_after("3") == 3
    assert 0 < parse_retry_after(format_datetime(datetime.now(UTC) + timedelta(seconds=60))) <= 60
    assert parse_retry_after(format_datetime(datetime.now(UTC) - timedelta(seconds=5))) == 0
    assert parse_retry_after("invalid") is None
    assert parse_retry_after(None) is None


async def test_network_failure_is_not_retried_and_marks_usage_unknown():
    def handler(request):
        raise httpx.ReadTimeout("private response", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = BailianClient(BailianSettings(_env_file=None), client)
        with pytest.raises(httpx.ReadTimeout):
            await provider.complete([])
    assert provider.metrics.attempts == 1 and provider.metrics.retries == 0
    assert not provider.metrics.usage_complete


async def test_large_stream_is_closed_before_consuming_remaining_chunks():
    class Chunks(httpx.AsyncByteStream):
        def __init__(self):
            self.read = 0
            self.closed = False

        async def __aiter__(self):
            for _ in range(4):
                self.read += 1
                yield b"x" * 150000

        async def aclose(self):
            self.closed = True

    stream = Chunks()
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, stream=stream),
        )
    ) as client:
        provider = BailianClient(BailianSettings(_env_file=None), client)
        with pytest.raises(ValueError, match="Oversized"):
            await provider.complete([])
    assert stream.read == 2 and stream.closed
    assert not provider.metrics.usage_complete


async def test_compressed_response_is_not_decoded_twice():
    import gzip

    payload = {"usage": {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6}}
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                content=gzip.compress(json.dumps(payload).encode()),
                headers={"Content-Encoding": "gzip"},
            )
        )
    ) as client:
        provider = BailianClient(BailianSettings(_env_file=None), client)
        assert await provider.complete([]) == payload
    assert provider.metrics.total_tokens == 6 and provider.metrics.usage_complete


def test_partial_and_invalid_usage_is_never_presented_as_complete():
    from backend.core.ai_metrics import AICallMetrics

    metrics = AICallMetrics()
    metrics.record_usage({"usage": {"prompt_tokens": 10, "completion_tokens": True}})
    assert metrics.prompt_tokens == 10 and metrics.completion_tokens == 0
    assert not metrics.usage_complete
    complete = AICallMetrics()
    complete.record_usage({"usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}})
    complete.record_usage({"usage": {"prompt_tokens": 20, "completion_tokens": 3, "total_tokens": 23}})
    assert complete.total_tokens == 35 and complete.usage_complete


async def test_retry_after_is_honored_and_retry_can_be_disabled():
    from unittest.mock import AsyncMock, patch

    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": "1"}) if len(calls) == 1 else httpx.Response(200, json={})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with patch("backend.infrastructure.bailian.asyncio.sleep", new_callable=AsyncMock) as sleep:
            await BailianClient(BailianSettings(_env_file=None), client).complete([])
        sleep.assert_awaited_once_with(1.0)
    calls.clear()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = BailianClient(BailianSettings(_env_file=None, max_retries=0), client)
        with pytest.raises(BailianAPIError):
            await provider.complete([])
    assert len(calls) == 1


async def test_total_deadline_cancels_slow_provider_and_records_attempt():
    import asyncio

    async def slow(request):
        await asyncio.sleep(0.1)
        return httpx.Response(200, json={})

    async with httpx.AsyncClient(transport=httpx.MockTransport(slow)) as client:
        provider = BailianClient(BailianSettings(_env_file=None, timeout_seconds=0.01), client)
        with pytest.raises(TimeoutError):
            await provider.complete([])
    assert provider.metrics.attempts == 1 and provider.metrics.retries == 0
    assert not provider.metrics.usage_complete
