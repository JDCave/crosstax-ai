"""Real HTTP contracts backed by an isolated rule database."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.engine.publication import RulePublisher
from backend.engine.rule_loader import RuleLoader
from backend.engine.validation import ValidationEngine
from backend.main import create_app
from backend.models import Base, RuleAuditRecord, RuleEngineState
from backend.services.rule_api import RuleAPIService, get_rule_api_service

PREFIX = "/api/v1/rule-engine"
BASE = json.loads(Path("assets/mock-data/cases.json").read_text())[0]["form_data"]


@pytest.fixture
async def api_client():
    database = create_async_engine(
        "sqlite+aiosqlite://", execution_options={"schema_translate_map": {"crosstax": None}}
    )
    try:
        async with database.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(database, expire_on_commit=False)
        async with sessions.begin() as session:
            session.add(RuleEngineState(id=1))
        publisher = RulePublisher(sessions)
        version = await publisher.register(json.loads(Path("rules/rules_global_v4.json").read_text()), [])
        await publisher.approve(version, {"review": "HTTP integration fixture"})
        await publisher.activate(version, 0)
        service = RuleAPIService(ValidationEngine(RuleLoader(sessions)))
        app = create_app()
        app.dependency_overrides[get_rule_api_service] = lambda: service
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            yield client, service
    finally:
        await database.dispose()


def payload():
    return {"form_data": BASE, "policy": {"today": "2026-11-03"}}


async def test_one_request_returns_result_without_persisting_or_requiring_session(api_client):
    client, service = api_client
    response = await client.post(PREFIX + "/validate", json=payload())
    assert response.status_code == 200, response.text
    original = response.json()
    assert original["verdict"] == "AUTO_PASS"
    assert original["issues"] == []
    assert original["execution"]["policy"]["today"] == "2026-11-03"
    assert "session_id" not in original and "result" not in original
    assert (await client.post(PREFIX + "/validate", json=payload())).json() == original
    async with service.engine.loader.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(RuleAuditRecord)) == 0
    # Each call evaluates the supplied data; there is no session collision mechanism.
    changed = payload() | {"form_data": BASE | {"holder_name": "Changed"}}
    assert (await client.post(PREFIX + "/validate", json=changed)).status_code == 200
    assert (await client.get(PREFIX + "/rules/current")).status_code == 404
    assert (await client.post(PREFIX + "/validations", json=payload())).status_code == 404


async def test_three_business_verdicts_are_successful_http_responses(api_client):
    client, _ = api_client
    cases = json.loads(Path("assets/mock-data/cases.json").read_text())
    for case in cases:
        request = payload() | {
            "form_data": case["form_data"],
            "indicia_issues": case["indicia_issues"],
        }
        response = await client.post(PREFIX + "/validate", json=request)
        assert response.status_code == 200
        assert response.json()["verdict"] == case["expected_verdict"]


async def test_invalid_requests_are_sanitized_and_bounded(api_client):
    client, _ = api_client
    bad = payload() | {"form_data": BASE | {"has_signature": "secret-marker"}}
    response = await client.post(PREFIX + "/validate", json=bad)
    assert response.status_code == 422
    assert "secret-marker" not in response.text
    assert set(response.json()) == {"code", "message", "details"}
    assert any(item["field"] == "form_data.has_signature" for item in response.json()["details"])
    response = await client.post(PREFIX + "/validate", content=b"{broken", headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    response = await client.post(PREFIX + "/validate", content=b" " * 1_048_577)
    assert response.status_code == 413
    invalid_policy = payload() | {"policy": {"today": "2026-11-03", "earliest_signing_date": "2027-01-01"}}
    assert (await client.post(PREFIX + "/validate", json=invalid_policy)).status_code == 422


async def test_unavailable_and_replay_mismatch_are_not_passes(api_client):
    client, service = api_client
    with patch.object(service.engine.loader, "refresh", AsyncMock(side_effect=ValueError("private-db-details"))):
        response = await client.post(PREFIX + "/validate", json=payload())
        assert response.status_code == 503
        assert "private-db-details" not in response.text
    assert (await client.post(PREFIX + "/validate", json=payload())).status_code == 200


def test_openapi_exposes_only_one_rule_engine_endpoint():
    paths = create_app().openapi()["paths"]
    assert [path for path in paths if path.startswith(PREFIX)] == [PREFIX + "/validate"]
    assert set(paths) == {PREFIX + "/validate"}
    app = create_app()
    assert app.redoc_url is None
    assert app.swagger_ui_oauth2_redirect_url is None


async def test_missing_active_rules_returns_503(api_client):
    client, service = api_client
    async with service.engine.loader.sessions.begin() as session:
        state = await session.get(RuleEngineState, 1)
        state.active_version_id = None
        state.activated_at = None
    response = await client.post(PREFIX + "/validate", json=payload())
    assert response.status_code == 503
    assert response.json()["code"] == "NO_ACTIVE_RULES"


async def test_streaming_body_limit_does_not_require_content_length(api_client):
    client, _ = api_client

    async def chunks():
        yield b" " * 600_000
        yield b" " * 600_000

    response = await client.post(PREFIX + "/validate", content=chunks(), headers={"Content-Type": "application/json"})
    assert response.status_code == 413


async def test_entity_form_does_not_require_invented_incorporation_date(api_client):
    client, _ = api_client
    form = json.loads(Path("assets/crs-templates/crs-entity-request.json").read_text())["form_data"]
    form.pop("holder_dob", None)
    response = await client.post(
        PREFIX + "/validate", json=payload() | {"form_data": form, "policy": {"today": "2026-11-04"}}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["verdict"] == "AUTO_PASS"
    assert next(c for c in body["check_items"] if c["check_id"] == "incorporation_date")["status"] == "NOT_APPLICABLE"
    form["incorporation_date"] = "not-a-date"
    assert (await client.post(PREFIX + "/validate", json=payload() | {"form_data": form})).json()[
        "verdict"
    ] == "NEED_USER_FIX"


async def test_multi_residence_fixed_snapshot_aggregate_and_paths(api_client):
    client, service = api_client
    form = dict(BASE)
    tax = {k: form.pop(k) for k in ("jurisdiction_code", "tin_type", "tin", "has_no_tin")}
    form["tax_residencies"] = [
        tax,
        {"jurisdiction_code": "HK", "tin_type": "HKID", "tin": "wrong", "has_no_tin": False},
    ]
    form["has_signature"] = False
    with patch.object(service.engine.loader, "refresh", wraps=service.engine.loader.refresh) as refresh:
        response = await client.post(PREFIX + "/validate", json=payload() | {"form_data": form})
    assert refresh.await_count == 1
    body = response.json()
    assert response.status_code == 200, body
    assert body["verdict"] == "NEED_USER_FIX"
    assert body["checks"] is None
    assert len(body["residence_results"]) == 2
    assert [r["checks"]["status"] for r in body["residence_results"]] == ["PASSED", "FAILED"]
    assert sum(i["code"] == "NO_SIGNATURE" for i in body["issues"]) == 1
    assert any(i["field"] == "tax_residencies.1.tin" for i in body["issues"])
    assert "entity_classification" in body["review_scope"]["not_evaluated"]
    assert body["guidance"]["status"] == "NOT_REQUESTED"
    form["tax_residencies"][1] = {"jurisdiction_code": "ZZ", "tin": "12345678", "has_no_tin": False}
    form["has_signature"] = True
    assert (await client.post(PREFIX + "/validate", json=payload() | {"form_data": form})).json()[
        "verdict"
    ] == "MANUAL_TRIAGE"
    form["tax_residencies"][1] = tax
    assert (await client.post(PREFIX + "/validate", json=payload() | {"form_data": form})).status_code == 422
    form["tax_residencies"] = []
    assert (await client.post(PREFIX + "/validate", json=payload() | {"form_data": form})).status_code == 422


async def test_guidance_disabled_fallback_preserves_upstream_provenance(api_client):
    from backend.agents.remediation import GuidanceSettings, RemediationAgent

    client, service = api_client
    service.agent = RemediationAgent(GuidanceSettings(enabled=False))
    issue = {"code": "TEAM_CHECK", "severity": "WARNING", "message": "Sensitive input", "confidence": 0.8}
    response = await client.post(
        PREFIX + "/validate",
        json=payload()
        | {
            "include_guidance": True,
            "indicia_issues": [issue],
        },
    )
    body = response.json()
    assert body["verdict"] == "MANUAL_TRIAGE"
    assert body["guidance"]["status"] == "FALLBACK"
    assert body["guidance"]["reason_code"] == "AI_NOT_CONFIGURED"
    assert body["issue_origins"] == [{"issue_index": 0, "source": "UPSTREAM", "evidence_ref": "issue:0"}]
    assert body["guidance"]["actions"][0]["evidence_refs"] == ["issue:0"]


async def test_individual_missing_dob_and_conflicting_entity_dates_are_business_issues(api_client):
    client, _ = api_client
    form = dict(BASE)
    form.pop("holder_dob", None)
    body = (await client.post(PREFIX + "/validate", json=payload() | {"form_data": form})).json()
    assert body["verdict"] == "NEED_USER_FIX"
    assert any(i["field"] == "holder_dob" for i in body["issues"])
    form = json.loads(Path("assets/crs-templates/crs-entity-request.json").read_text())["form_data"]
    form["holder_dob"] = "2020-06-15"
    form["incorporation_date"] = "2021-06-15"
    body = (
        await client.post(
            PREFIX + "/validate",
            json=payload()
            | {
                "form_data": form,
                "policy": {"today": "2026-11-04"},
            },
        )
    ).json()
    assert any(i["code"] == "INCONSISTENT_DATE" for i in body["issues"])


@pytest.mark.parametrize("name", ["individual", "entity", "multi-residence"])
async def test_documented_samples_are_callable_and_match_guides(api_client, name):
    from backend.agents.remediation import GuidanceSettings, RemediationAgent

    client, service = api_client
    service.agent = RemediationAgent(GuidanceSettings(enabled=False))
    raw = Path(f"assets/crs-templates/crs-{name}-request.json").read_text().strip()
    assert raw in Path("assets/crs-templates/API_INTEGRATION.md").read_text()
    response = await client.post(PREFIX + "/validate", json=json.loads(raw))
    assert response.status_code == 200, response.text
    assert response.json()["verdict"] == "AUTO_PASS"
    assert all(r["checks"]["verification_level"] == "FORMAT_ONLY" for r in response.json()["residence_results"])


def test_openapi_snapshot_matches_runtime():
    assert json.loads(Path("backend/api/openapi.json").read_text()) == create_app().openapi()


async def test_http_agent_reads_same_rule_snapshot_and_preserves_blocking_verdict(api_client):
    from pydantic import SecretStr

    from backend.agents.remediation import GuidanceSettings, RemediationAgent

    client, service = api_client
    sent = []

    def provider(request):
        sent.append(request.content.decode())
        if len(sent) == 1:
            message = {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": name,
                        "type": "function",
                        "function": {
                            "name": name,
                            "arguments": '{"issue_index":0}',
                        },
                    }
                    for name in ("get_validation_evidence", "get_rule_details")
                ],
            }
        else:
            message = {
                "role": "assistant",
                "content": json.dumps(
                    {
                        "summary": "请补正格式问题。",
                        "actions": [
                            {
                                "issue_index": 0,
                                "field": "tin",
                                "instruction": "请对照原始证件核对号码格式。",
                                "evidence_refs": ["issue:0", "rule:0"],
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
            }
        return httpx.Response(200, json={"choices": [{"message": message}]})

    service.agent = RemediationAgent(
        GuidanceSettings(enabled=True, api_key=SecretStr("mock"), model="mock-model"), httpx.MockTransport(provider)
    )
    body = json.loads(Path("assets/crs-templates/crs-individual-request.json").read_text())
    body["form_data"]["tin"] = "SECRET-WRONG-TIN"
    body["include_guidance"] = True
    with patch.object(service.engine.loader, "refresh", wraps=service.engine.loader.refresh) as refresh:
        response = await client.post(PREFIX + "/validate", json=body)
    result = response.json()
    assert refresh.await_count == 1
    assert result["verdict"] == "NEED_USER_FIX"
    assert result["issues"][0]["severity"] == "BLOCKER"
    assert result["guidance"]["status"] == "GENERATED"
    assert "SECRET-WRONG-TIN" not in "".join(sent)
    tool_messages = json.loads(sent[-1])["messages"]
    tool_rule = json.loads(next(m["content"] for m in tool_messages if m.get("tool_call_id") == "get_rule_details"))
    assert tool_rule["rule_id"] == result["residence_results"][0]["checks"]["rule_id"]
