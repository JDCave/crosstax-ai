"""Real API/worker integration, frozen execution, recovery and privacy boundaries."""

import asyncio
import json
from datetime import timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr

from backend.core.rule_tasks import RuleTaskSettings
from backend.infrastructure.rule_tasks import utcnow
from backend.models import RuleEngineState, RuleValidationTask
from backend.services.rule_tasks import TaskService, get_task_service
from backend.workers.rule_tasks import RuleTaskWorker
from tests.backend import test_rule_engine_api as api_fixtures

api_client = api_fixtures.api_client
PREFIX = "/api/v1/rule-engine/tasks"


@pytest.fixture
async def task_api(api_client):
    client, api = api_client
    settings = RuleTaskSettings(_env_file=None, encryption_keys=[SecretStr(Fernet.generate_key().decode())])
    service = TaskService(api, settings)
    client._transport.app.dependency_overrides[get_task_service] = lambda: service
    return client, service, RuleTaskWorker(service)


def payload():
    return {"session_id": str(uuid4()), "validation": api_fixtures.payload()}


async def submit(client, request=None, key=None):
    response = await client.post(PREFIX, json=request or payload(), headers={"Idempotency-Key": key or str(uuid4())})
    assert response.status_code == 202, response.text
    return response


async def test_submit_is_durable_then_worker_returns_same_contract(task_api):
    client, service, worker = task_api
    response = await submit(client)
    body = response.json()
    assert body["status"] == "PENDING" and body["result"] is None
    saved = await service.repository.get(body["task_id"])
    assert saved.status == "PENDING" and saved.payload_ciphertext
    assert api_fixtures.BASE["tin"] not in saved.payload_ciphertext
    location = response.headers["Location"]
    assert (await client.get(location)).json()["status"] == "PENDING"
    assert await worker.run_once()
    result = await client.get(location)
    assert result.headers["Cache-Control"] == "no-store"
    data = result.json()
    assert data["status"] == "SUCCEEDED" and data["result"]["verdict"] == "AUTO_PASS"
    synchronous = await client.post("/api/v1/rule-engine/validate", json=api_fixtures.payload())
    assert data["result"] == synchronous.json()
    saved = await service.repository.get(body["task_id"])
    assert '"verdict"' not in saved.result_ciphertext


async def test_business_fix_is_success_and_all_five_cases_work(task_api):
    client, _, worker = task_api
    cases = json.loads(Path("assets/mock-data/cases.json").read_text())
    for case in cases:
        request = payload()
        request["validation"].update(form_data=case["form_data"], indicia_issues=case["indicia_issues"])
        response = await submit(client, request)
        await worker.run_once()
        data = (await client.get(response.headers["Location"])).json()
        assert data["status"] == "SUCCEEDED", data
        assert data["result"]["verdict"] == case["expected_verdict"]


async def test_idempotency_survives_reload_conflicts_and_capacity(task_api):
    client, service, _ = task_api
    request, key = payload(), str(uuid4())
    first = await submit(client, request, key)
    with patch.object(service.api.engine.loader, "refresh", AsyncMock(side_effect=ValueError("unavailable"))):
        duplicate = await submit(client, request, key)
    assert duplicate.json()["task_id"] == first.json()["task_id"]
    request["validation"]["form_data"] = api_fixtures.BASE | {"holder_name": "different"}
    conflict = await client.post(PREFIX, json=request, headers={"Idempotency-Key": key})
    assert conflict.status_code == 409
    service.settings.capacity = 1
    full = await client.post(PREFIX, json=payload(), headers={"Idempotency-Key": str(uuid4())})
    assert full.status_code == 503 and full.headers["Retry-After"] == "1"


async def test_structured_policy_and_rules_are_frozen(task_api):
    client, service, worker = task_api
    validation = json.loads(Path("assets/crs-templates/crs-structured-individual-request.json").read_text())
    response = await submit(client, {"session_id": str(uuid4()), "validation": validation})
    original = response.json()
    # Live rules and policy disappear after admission; neither may be read by the worker.
    async with service.repository.sessions.begin() as session:
        state = await session.get(RuleEngineState, 1)
        state.active_version_id = None
        state.activated_at = None
    with patch("backend.engine.structured_validation.load_form_policy", side_effect=ValueError("changed")):
        await worker.run_once()
    body = (await client.get(response.headers["Location"])).json()
    assert body["status"] == "SUCCEEDED", body
    assert body["result"]["rule_version_id"] == original["rule_version_id"]
    assert body["result"]["execution"]["form_policy_id"]


async def test_invalid_unknown_expired_and_missing_config(task_api):
    client, service, _ = task_api
    assert (await client.post(PREFIX, json=payload())).status_code == 422
    request = payload()
    request["deadline_at"] = "2020-01-01T00:00:00Z"
    assert (await client.post(PREFIX, json=request, headers={"Idempotency-Key": str(uuid4())})).status_code == 422
    request["deadline_at"] = "2027-01-01T00:00:00"  # Must carry a timezone.
    assert (await client.post(PREFIX, json=request, headers={"Idempotency-Key": str(uuid4())})).status_code == 422
    assert (await client.get(PREFIX + "/" + str(uuid4()))).status_code == 404
    response = await submit(client)
    async with service.repository.sessions.begin() as session:
        row = await session.get(RuleValidationTask, response.json()["task_id"])
        row.expires_at = utcnow() - timedelta(seconds=1)
    assert (await client.get(response.headers["Location"])).status_code == 410
    service.settings.encryption_keys = []
    assert (await client.post(PREFIX, json=payload(), headers={"Idempotency-Key": str(uuid4())})).status_code == 503
    assert (await client.post("/api/v1/rule-engine/validate", json=api_fixtures.payload())).status_code == 200


async def test_worker_failure_build_mismatch_and_secret_redaction(task_api):
    client, service, worker = task_api
    response = await submit(client)
    with patch.object(service.api, "validate_frozen", AsyncMock(side_effect=RuntimeError("secret-marker"))):
        await worker.run_once()
    body = (await client.get(response.headers["Location"])).json()
    assert body["status"] == "FAILED" and body["error"]["code"] == "TASK_EXECUTION_FAILED"
    assert "secret-marker" not in json.dumps(body)
    response = await submit(client)
    with patch("backend.workers.rule_tasks.task_build_id", return_value="different"):
        await worker.run_once()
    body = (await client.get(response.headers["Location"])).json()
    assert body["error"]["code"] == "TASK_BUILD_MISMATCH"


async def test_heartbeat_and_deadline_include_queue_time(task_api):
    client, service, worker = task_api
    request = payload()
    request["deadline_at"] = (utcnow() + timedelta(seconds=0.35)).isoformat()
    response = await submit(client, request)
    original = service.api.validate_frozen
    service.settings.heartbeat_seconds = 0.05

    async def slow(*args, **kwargs):
        await asyncio.sleep(0.1)
        return await original(*args, **kwargs)

    with patch.object(service.api, "validate_frozen", slow), patch.object(
        service.repository, "renew", wraps=service.repository.renew
    ) as renew:
        await worker.run_once()
        assert renew.call_count >= 1
    assert (await client.get(response.headers["Location"])).json()["status"] == "SUCCEEDED"
    request["deadline_at"] = (utcnow() + timedelta(seconds=0.03)).isoformat()
    response = await submit(client, request)
    await asyncio.sleep(0.04)  # Deadline already consumed by the queue.
    assert not await worker.run_once()
    body = (await client.get(response.headers["Location"])).json()
    assert body["status"] == "FAILED" and body["result"] is None


async def test_heartbeat_loss_prevents_stale_completion_and_allows_recovery(task_api):
    client, service, worker = task_api
    response = await submit(client)
    original = service.api.validate_frozen
    service.settings.heartbeat_seconds = 0.01

    async def slow(*args, **kwargs):
        await asyncio.sleep(0.08)
        return await original(*args, **kwargs)

    with patch.object(service.api, "validate_frozen", slow), patch.object(
        service.repository, "renew", AsyncMock(return_value=False)
    ):
        await worker.run_once()
    row = await service.repository.get(response.json()["task_id"])
    assert row.status == "RUNNING" and row.result_ciphertext is None
    async with service.repository.sessions.begin() as session:
        saved = await session.get(RuleValidationTask, row.task_id)
        saved.lease_until = utcnow() - timedelta(seconds=1)
    await worker.run_once()
    body = (await client.get(response.headers["Location"])).json()
    assert body["status"] == "SUCCEEDED"
    assert (await service.repository.get(row.task_id)).attempts == 2


async def test_execution_timeout_never_commits_success_and_redacts_bad_input(task_api):
    client, service, worker = task_api
    request = payload()
    request["deadline_at"] = (utcnow() + timedelta(seconds=0.05)).isoformat()
    response = await submit(client, request)

    async def slow(*args, **kwargs):
        await asyncio.sleep(10)

    with patch.object(service.api, "validate_frozen", slow):
        await worker.run_once()
    await worker.run_once()  # Recovery scan terminalizes deadline-expired leases.
    body = (await client.get(response.headers["Location"])).json()
    assert body["status"] == "FAILED" and body["result"] is None
    request = payload()
    request["validation"]["form_data"] = api_fixtures.BASE | {"secret-marker": "secret-value"}
    response = await client.post(PREFIX, json=request, headers={"Idempotency-Key": str(uuid4())})
    assert response.status_code == 422
    assert "secret-marker" not in response.text and "secret-value" not in response.text
    assert "validation.form_data.<unknown>" in response.text


async def test_active_rules_unavailable_and_key_rotation(task_api):
    client, service, worker = task_api
    request, key = payload(), str(uuid4())
    response = await submit(client, request, key)
    service.settings.encryption_keys.insert(0, SecretStr(Fernet.generate_key().decode()))
    assert (await submit(client, request, key)).json()["task_id"] == response.json()["task_id"]
    await worker.run_once()
    assert (await client.get(response.headers["Location"])).json()["status"] == "SUCCEEDED"
    async with service.repository.sessions.begin() as session:
        state = await session.get(RuleEngineState, 1)
        state.active_version_id = None
        state.activated_at = None
    unavailable = await client.post(PREFIX, json=payload(), headers={"Idempotency-Key": str(uuid4())})
    assert unavailable.status_code == 503 and unavailable.json()["code"] == "NO_ACTIVE_RULES"
