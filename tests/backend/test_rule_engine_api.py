"""Real HTTP contracts backed by an isolated rule database."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.engine.audit_service import AuditValidationService
from backend.engine.publication import RulePublisher
from backend.engine.rule_loader import RuleLoader
from backend.engine.validation import ValidationEngine
from backend.main import create_app
from backend.models import Base, RuleEngineState
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
        service = RuleAPIService(AuditValidationService(ValidationEngine(RuleLoader(sessions))))
        app = create_app()
        app.dependency_overrides[get_rule_api_service] = lambda: service
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            yield client, service
    finally:
        await database.dispose()


def payload(session_id="api-demo"):
    return {"session_id": session_id, "form_data": BASE, "policy": {"today": "2026-11-03"}}


async def test_validate_get_retry_replay_and_coverage(api_client):
    client, _ = api_client
    response = await client.post(PREFIX + "/validations", json=payload())
    assert response.status_code == 200, response.text
    original = response.json()
    assert original["result"]["verdict"] == "AUTO_PASS"
    assert original["result"]["execution"]["policy"]["today"] == "2026-11-03"
    assert (await client.get(PREFIX + "/validations/api-demo")).json() == original
    assert (await client.post(PREFIX + "/validations", json=payload())).json() == original
    assert (await client.post(PREFIX + "/validations/api-demo/replay")).json() == original
    changed = payload() | {"form_data": BASE | {"holder_name": "Changed"}}
    assert (await client.post(PREFIX + "/validations", json=changed)).status_code == 409
    assert (await client.get(PREFIX + "/validations/missing")).status_code == 404
    current = await client.get(PREFIX + "/rules/current")
    assert current.json()["rule_count"] == 66
    coverage = (await client.get(PREFIX + "/rules/coverage")).json()
    assert len(coverage["rules"]) == 66
    assert coverage["rule_version_id"] == original["result"]["rule_version_id"]


async def test_three_business_verdicts_are_successful_http_responses(api_client):
    client, _ = api_client
    cases = json.loads(Path("assets/mock-data/cases.json").read_text())
    for case in cases:
        request = payload("case-" + case["case_id"]) | {
            "form_data": case["form_data"],
            "indicia_issues": case["indicia_issues"],
        }
        response = await client.post(PREFIX + "/validations", json=request)
        assert response.status_code == 200
        assert response.json()["result"]["verdict"] == case["expected_verdict"]


async def test_invalid_requests_are_sanitized_and_bounded(api_client):
    client, _ = api_client
    bad = payload() | {"form_data": BASE | {"has_signature": "secret-marker"}}
    response = await client.post(PREFIX + "/validations", json=bad)
    assert response.status_code == 422
    assert "secret-marker" not in response.text
    assert set(response.json()) == {"code", "message"}
    response = await client.post(
        PREFIX + "/validations", content=b"{broken", headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 422
    response = await client.post(PREFIX + "/validations", content=b" " * 1_048_577)
    assert response.status_code == 413
    invalid_policy = payload() | {"policy": {"today": "2026-11-03", "earliest_signing_date": "2027-01-01"}}
    assert (await client.post(PREFIX + "/validations", json=invalid_policy)).status_code == 422


async def test_unavailable_and_replay_mismatch_are_not_passes(api_client):
    client, service = api_client
    with patch.object(service.audit.engine.loader, "refresh", AsyncMock(side_effect=ValueError("private-db-details"))):
        response = await client.post(PREFIX + "/validations", json=payload())
        assert response.status_code == 503
        assert "private-db-details" not in response.text
    assert (await client.post(PREFIX + "/validations", json=payload())).status_code == 200
    with patch.object(service.audit, "replay_stored", AsyncMock(side_effect=ValueError("wrong-build"))):
        assert (await client.post(PREFIX + "/validations/api-demo/replay")).status_code == 409


def test_openapi_declares_all_endpoints():
    paths = create_app().openapi()["paths"]
    assert PREFIX + "/validations" in paths
    assert PREFIX + "/rules/coverage" in paths
    assert "/health" in paths and "/ready" in paths


async def test_missing_active_rules_is_503_but_stored_results_remain_readable(api_client):
    client, service = api_client
    original = await client.post(PREFIX + "/validations", json=payload())
    assert original.status_code == 200
    async with service.audit.sessions.begin() as session:
        state = await session.get(RuleEngineState, 1)
        state.active_version_id = None
        state.activated_at = None
    assert (await client.get(PREFIX + "/rules/current")).status_code == 503
    assert (await client.post(PREFIX + "/validations", json=payload("new-session"))).status_code == 503
    assert (await client.get(PREFIX + "/validations/api-demo")).json() == original.json()


async def test_streaming_body_limit_does_not_require_content_length(api_client):
    client, _ = api_client

    async def chunks():
        yield b" " * 600_000
        yield b" " * 600_000

    response = await client.post(
        PREFIX + "/validations", content=chunks(), headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 413
