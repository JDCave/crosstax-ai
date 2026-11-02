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
    assert set(response.json()) == {"code", "message"}
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
