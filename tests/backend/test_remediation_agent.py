"""Exercise tool orchestration, evidence binding, privacy and failure isolation without external APIs."""

import asyncio
import json
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr

from backend.agents.remediation import GuidanceSettings, RemediationAgent
from backend.engine.contracts import AuditIssue, CRSFormData, ValidationPolicy
from backend.engine.document_validation import validate_document
from backend.engine.reproducibility import canonical_hash
from backend.engine.rule_loader import compile_snapshot
from backend.engine.validation import ValidationEngine


@pytest.fixture
def evaluation():
    rules = json.loads(Path("rules/rules_global_v4.json").read_text())
    snapshot = compile_snapshot(canonical_hash(rules), 3, rules)
    form = json.loads(Path("assets/crs-templates/crs-individual-request.json").read_text())["form_data"]
    form.update(holder_name="PRIVATE NAME", residence_address="PRIVATE ADDRESS", tin="PRIVATE TIN")
    engine = ValidationEngine(None)
    policy = ValidationPolicy.model_validate({"today": "2026-11-04"})
    result = validate_document(engine, CRSFormData(**form), policy, snapshot, [])
    assert len(result.form_issues) == 1
    return result, snapshot


def settings(**kwargs):
    return GuidanceSettings(enabled=True, model="mock-model", api_key=SecretStr("mock-key"), **kwargs)


def envelope(message):
    return httpx.Response(200, json={"choices": [{"message": message}]})


def tools(*names):
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": f"call-{i}",
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": '{"issue_index":0}',
                },
            }
            for i, name in enumerate(names)
        ],
    }


def answer(refs=None):
    return {
        "role": "assistant",
        "content": json.dumps(
            {
                "summary": "请核对号码原始资料。",
                "actions": [
                    {
                        "issue_index": 0,
                        "field": "tin",
                        "instruction": "请核对税号格式并根据原始资料补正。",
                        "evidence_refs": refs or ["issue:0", "rule:0"],
                    }
                ],
            },
            ensure_ascii=False,
        ),
    }


async def test_agent_uses_tools_fixed_evidence_and_never_sends_personal_data(evaluation):
    result, snapshot = evaluation
    requests = []

    def handler(request):
        requests.append(request.content.decode())
        if len(requests) == 1:
            return envelope(tools("get_validation_evidence", "get_rule_details", "get_source_excerpt"))
        return envelope(answer())

    agent = RemediationAgent(settings(), httpx.MockTransport(handler))
    guidance = await agent.generate(result, snapshot, True)
    assert guidance.status == "GENERATED"
    assert guidance.model == "mock-model"
    assert guidance.output_fingerprint and guidance.prompt_fingerprint
    assert len(requests) == 2
    assert "tools" in json.loads(requests[0])
    assert "response_format" not in json.loads(requests[0])
    assert "tools" not in json.loads(requests[1])
    assert json.loads(requests[1])["response_format"] == {"type": "json_object"}
    assert all(marker not in "".join(requests) for marker in ("PRIVATE NAME", "PRIVATE ADDRESS", "PRIVATE TIN"))
    tool_messages = json.loads(requests[-1])["messages"]
    details = json.loads(next(m["content"] for m in tool_messages if m.get("tool_call_id") == "call-1"))
    assert details["rule_id"] == "HK_HKID_INDIVIDUAL"
    assert details["source_section"]
    assert json.loads(tool_messages[-1]["content"])["available"] is False
    assert result.verdict == "NEED_USER_FIX"


@pytest.mark.parametrize(
    "failure", ["citation", "field", "no_tools", "bad_json", "tool", "verdict", "number", "missing"]
)
async def test_invalid_advice_falls_back_without_changing_result(evaluation, failure):
    result, snapshot = evaluation
    count = 0

    def handler(request):
        nonlocal count
        count += 1
        if count == 1 and failure != "no_tools":
            return envelope(tools("unknown_tool" if failure == "tool" else "get_validation_evidence"))
        message = answer(["issue:0"])
        if failure == "bad_json":
            message["content"] = "not json"
        else:
            body = json.loads(message["content"])
            if failure == "citation":
                body["actions"][0]["evidence_refs"].append("rule:999")
            if failure == "field":
                body["actions"][0]["field"] = "holder_name"
            if failure == "verdict":
                body["summary"] = "AUTO_PASS"
            if failure == "number":
                body["actions"][0]["instruction"] = "改为12345678"
            if failure == "missing":
                body["actions"] = []
            message["content"] = json.dumps(body)
        return envelope(message)

    original = result.model_dump()
    guidance = await RemediationAgent(settings(), httpx.MockTransport(handler)).generate(result, snapshot, True)
    assert guidance.status == "FALLBACK"
    assert guidance.reason_code == "AI_INVALID_RESPONSE"
    assert guidance.actions[0].evidence_refs == ["issue:0"]
    assert result.model_dump() == original


async def test_timeout_and_http_errors_are_bounded_fallbacks(evaluation):
    result, snapshot = evaluation

    async def slow(request):
        await asyncio.sleep(0.1)
        return envelope(answer())

    agent = RemediationAgent(settings(timeout_seconds=0.01), httpx.MockTransport(slow))
    assert (await agent.generate(result, snapshot, True)).reason_code == "AI_TIMEOUT"
    agent = RemediationAgent(settings(), httpx.MockTransport(lambda request: httpx.Response(503)))
    assert (await agent.generate(result, snapshot, True)).status == "FALLBACK"


async def test_upstream_text_is_not_sent_and_large_issue_lists_fall_back(evaluation):
    result, snapshot = evaluation
    upstream = AuditIssue(
        code="PRIVATE CODE", field="PRIVATE FIELD", message="PRIVATE MESSAGE", severity="WARNING", confidence=0.8
    )
    updated = result.model_copy(update={"form_issues": (), "indicia_issues": (upstream,)})
    requests = []

    def handler(request):
        requests.append(request.content.decode())
        if len(requests) == 1:
            return envelope(tools("get_validation_evidence"))
        message = answer(["issue:0"])
        body = json.loads(message["content"])
        body["actions"][0]["field"] = None
        message["content"] = json.dumps(body)
        return envelope(message)

    guidance = await RemediationAgent(settings(), httpx.MockTransport(handler)).generate(updated, snapshot, True)
    assert guidance.status == "GENERATED"
    assert guidance.actions[0].field == "PRIVATE FIELD"
    assert "PRIVATE" not in "".join(requests)
    large = result.model_copy(update={"indicia_issues": tuple([upstream] * 100)})
    fallback = await RemediationAgent(GuidanceSettings(enabled=False)).generate(large, snapshot, True)
    assert len(fallback.actions) == 101


async def test_loop_budget_and_malformed_provider_payload(evaluation):
    result, snapshot = evaluation
    agent = RemediationAgent(settings(), httpx.MockTransport(lambda request: envelope(tools("get_rule_details"))))
    assert (await agent.generate(result, snapshot, True)).status == "FALLBACK"
    agent = RemediationAgent(settings(), httpx.MockTransport(lambda request: httpx.Response(200, json={"choices": []})))
    assert (await agent.generate(result, snapshot, True)).status == "FALLBACK"


async def test_concurrency_limit_and_uninspected_rule_reference(evaluation):
    result, snapshot = evaluation
    active = peak = 0

    async def handler(request):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.005)
        active -= 1
        messages = json.loads(request.content)["messages"]
        if len(messages) == 2:
            return envelope(tools("get_validation_evidence"))
        # A real rule ref is rejected too if that rule was not actually inspected.
        return envelope(answer())

    agent = RemediationAgent(settings(max_concurrency=1), httpx.MockTransport(handler))
    responses = await asyncio.gather(agent.generate(result, snapshot, True), agent.generate(result, snapshot, True))
    assert peak == 1
    assert all(response.status == "FALLBACK" for response in responses)


async def test_truncated_generation_and_unexpected_sdk_shape_are_isolated(evaluation):
    result, snapshot = evaluation
    for body in [
        {"choices": [{"message": answer(["issue:0"]), "finish_reason": "length"}]},
        {"choices": [123]},
    ]:
        agent = RemediationAgent(
            settings(), httpx.MockTransport(lambda request, body=body: httpx.Response(200, json=body))
        )
        assert (await agent.generate(result, snapshot, True)).status == "FALLBACK"


@pytest.mark.parametrize("status,reason", [(401, "AI_AUTHENTICATION_FAILED"), (429, "AI_RATE_LIMITED")])
async def test_bailian_errors_preserve_rules_and_return_actionable_reason(evaluation, status, reason):
    result, snapshot = evaluation
    agent = RemediationAgent(
        settings(),
        httpx.MockTransport(
            lambda request: httpx.Response(status, json={"message": "private provider body"}),
        ),
    )
    guidance = await agent.generate(result, snapshot, True)
    assert guidance.status == "FALLBACK"
    assert guidance.reason_code == reason
    assert result.verdict == "NEED_USER_FIX"
    assert "private provider body" not in guidance.model_dump_json()


async def test_bailian_key_missing_never_calls_provider(evaluation, monkeypatch):
    monkeypatch.delenv("RULE_AI_API_KEY", raising=False)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    result, snapshot = evaluation

    def forbidden(request):
        raise AssertionError("Missing keys must not make a network request")

    agent = RemediationAgent(GuidanceSettings(_env_file=None), httpx.MockTransport(forbidden))
    assert (await agent.generate(result, snapshot, True)).reason_code == "AI_NOT_CONFIGURED"
    assert (await agent.generate(result, snapshot, False)).status == "NOT_REQUESTED"


async def test_no_issues_uses_json_stage_without_tool_round(evaluation):
    result, snapshot = evaluation
    passed = result.model_copy(
        update={"form_issues": (), "indicia_issues": (), "issue_origins": [], "verdict": "AUTO_PASS"}
    )
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        return envelope(
            {"role": "assistant", "content": '{"summary":"当前已执行检查无异常, 仍需关注未评估范围。","actions":[]}'}
        )

    guidance = await RemediationAgent(settings(), httpx.MockTransport(handler)).generate(passed, snapshot, True)
    assert guidance.status == "GENERATED"
    assert len(requests) == 1 and "tools" not in requests[0]
    assert requests[0]["response_format"] == {"type": "json_object"}


async def test_network_and_internal_failures_are_distinct(evaluation):
    from unittest.mock import AsyncMock, patch

    result, snapshot = evaluation

    def disconnected(request):
        raise httpx.ConnectError("PRIVATE CONNECTION DETAILS", request=request)

    agent = RemediationAgent(settings(), httpx.MockTransport(disconnected))
    guidance = await agent.generate(result, snapshot, True)
    assert guidance.error.category == "connection" and guidance.error.retryable
    assert guidance.reason_code == "AI_CONNECTION_ERROR"
    assert "PRIVATE" not in guidance.model_dump_json()
    with patch.object(agent, "_run", AsyncMock(side_effect=RuntimeError("PRIVATE BUG"))):
        guidance = await agent.generate(result, snapshot, True)
    assert guidance.reason_code == "AI_INTERNAL_ERROR"
    assert guidance.error.category == "internal" and not guidance.error.retryable
    assert "PRIVATE" not in guidance.model_dump_json()


async def test_auth_rate_quota_and_output_have_consistent_public_error_metadata(evaluation):
    result, snapshot = evaluation
    responses = [
        (httpx.Response(401, json={}), "authentication", False),
        (httpx.Response(429, json={}), "rate_limit", True),
        (httpx.Response(429, json={"error": {"code": "insufficient_quota"}}), "quota", False),
        (httpx.Response(200, json={"choices": []}), "invalid_response", False),
    ]
    for response, category, retryable in responses:
        agent = RemediationAgent(settings(), httpx.MockTransport(lambda request, response=response: response))
        guidance = await agent.generate(result, snapshot, True)
        assert guidance.status == "FALLBACK"
        assert guidance.error.category == category
        assert guidance.error.retryable is retryable
        assert result.verdict == "NEED_USER_FIX"
