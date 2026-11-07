"""Competition presentation, correction comparisons and safe empty-db initialization."""

import os
import json
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.core.competition import DemoSettings, SetupSettings, get_demo_settings, get_setup_settings
from backend.engine.contracts import AuditIssue
from backend.infrastructure.exceptions import AppException
from backend.main import create_app
from backend.models import RuleEngineState, RulePDFReport, RulePublication, RuleSource, RuleValidationTask, RuleVersion
from backend.services.competition import InitializationService, get_initialization_service
from backend.services.presentation import explanation_cards
from backend.services.task_comparison import compare_tasks
from tests.backend import test_rule_tasks as task_fixtures

api_client = task_fixtures.api_client
task_api = task_fixtures.task_api


async def finish(client, worker, request):
    response = await task_fixtures.submit(client, request)
    assert await worker.run_once()
    return response.headers["Location"], (await client.get(response.headers["Location"])).json()


async def test_correction_cards_and_same_session_comparison(task_api):
    client, _, worker = task_api
    request = task_fixtures.payload()
    request["validation"]["form_data"] = request["validation"]["form_data"] | {"has_signature": False}
    old_url, before = await finish(client, worker, request)
    card = before["result"]["explanation_cards"][0]
    assert card["severity"] == "BLOCKER" and card["action_source"] == "RULE" and card["evidence_refs"]
    assert "签署" in card["title"] and not card["rule_evidence"]  # Never invent a TIN URL for a signature issue.
    request["validation"]["form_data"]["has_signature"] = True
    new_url, after = await finish(client, worker, request)
    compared = await client.get(new_url, params={"compare_to":before["task_id"]})
    assert compared.status_code == 200, compared.text
    summary = compared.json()["comparison"]
    assert summary["context"] == "SAME_CONTEXT"
    assert summary["before_verdict"] == "NEED_USER_FIX" and summary["after_verdict"] == "AUTO_PASS"
    assert "form_data.has_signature" in summary["changed_fields"]
    assert summary["resolved"][0]["code"] == "NO_SIGNATURE"
    assert not summary["introduced"]
    assert request["validation"]["form_data"]["tin"] not in json.dumps(summary)
    assert (await client.get(old_url)).json()["result"] == before["result"]
    assert (await client.get(new_url)).json()["comparison"] is None


async def test_comparison_context_errors_and_duplicate_findings(task_api):
    client, service, worker = task_api
    request = task_fixtures.payload()
    old_url, before = await finish(client, worker, request)
    request["validation"]["policy"]["today"] = "2026-11-04"
    new_url, after = await finish(client, worker, request)
    summary = (await client.get(new_url, params={"compare_to":before["task_id"]})).json()["comparison"]
    assert summary["context"] == "DIFFERENT_CONTEXT" and "POLICY" in summary["context_changes"]
    assert (await client.get(new_url, params={"compare_to":after["task_id"]})).status_code == 422
    unrelated_url, unrelated = await finish(client, worker, task_fixtures.payload())
    assert (await client.get(unrelated_url, params={"compare_to":before["task_id"]})).status_code == 409
    pending = await task_fixtures.submit(client, request)
    assert (await client.get(pending.headers["Location"], params={"compare_to":before["task_id"]})).status_code == 409
    first, second = await service.get(before["task_id"]), await service.get(after["task_id"])
    issue = AuditIssue(code="DUPLICATE", severity="WARNING", field="tin", message="test", confidence=1)
    first.result.issues = [issue, issue]
    second.result.issues = [issue]
    compared = compare_tasks(first, second, request["validation"], request["validation"])
    assert compared.resolved[0].count == 1 and compared.remaining[0].count == 1


async def test_agent_action_card_uses_existing_evidence_only(task_api):
    from backend.agents.remediation import GuidanceAction
    client, service, worker = task_api
    request = task_fixtures.payload()
    request["validation"]["form_data"] = request["validation"]["form_data"] | {"has_signature":False}
    _, task = await finish(client, worker, request)
    result = (await service.get(task["task_id"])).result
    verdict = result.verdict
    result.guidance.status = "GENERATED"
    result.guidance.actions = [GuidanceAction(issue_index=0,field="has_signature",instruction="核实签署原件",evidence_refs=["issue:0"])]
    assert explanation_cards(result)[0].action_source == "AGENT"
    result.guidance.actions[0].evidence_refs = ["issue:99"]
    assert explanation_cards(result)[0].action_source == "RULE"
    assert result.verdict == verdict


async def test_demo_is_opt_in_read_only_and_explicitly_simulated(task_api, monkeypatch):
    client, service, _ = task_api
    route = "/api/v1/rule-engine/demo/upgrade-impact"
    assert (await client.get(route)).status_code == 404
    monkeypatch.setattr("backend.api.routes.competition.get_demo_settings", lambda:DemoSettings(_env_file=None,enabled=True))
    before = await service.api.engine.loader.refresh()
    response = await client.get(route)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["simulation"] is True and data["impact"]["sample_count"] == 5
    case_e = next(case for case in data["impact"]["cases"] if case["case_id"]=="E")
    assert case_e["changed"] and case_e["before"]["verdict"] != case_e["after"]["verdict"]
    assert (await service.api.engine.loader.refresh()).version_id == before.version_id


@pytest.fixture(params=["sqlite", "postgresql"])
async def empty_setup(tmp_path, monkeypatch, request):
    pg = request.param == "postgresql"
    url = os.getenv("CROSSTAX_TEST_DATABASE_URL") if pg else f"sqlite+aiosqlite:///{tmp_path / 'empty.db'}"
    if not url:
        pytest.skip("Configure an isolated PostgreSQL test connection")
    schema = "crosstax_test_setup_" + uuid4().hex if pg else None
    database = create_async_engine(url, execution_options={"schema_translate_map":{"crosstax":schema}})
    sessions = async_sessionmaker(database, expire_on_commit=False)
    service = InitializationService(database,sessions,tmp_path / "setup.lock")
    app = create_app()
    app.dependency_overrides[get_initialization_service] = lambda:service
    settings = SetupSettings(_env_file=None,enabled=False,token=SecretStr("competition-test-token-12345678"))
    monkeypatch.setattr("backend.api.routes.competition.get_setup_settings",lambda:settings)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://test") as client:
            yield client,service,settings
    finally:
        if pg:
            from sqlalchemy.schema import DropSchema
            async with database.begin() as connection:
                await connection.execute(DropSchema(schema, cascade=True, if_exists=True))
        await database.dispose()


async def test_initialization_disabled_token_and_empty_database_flow(empty_setup):
    client, service, settings = empty_setup
    path = "/api/v1/rule-engine/setup/initialize"
    assert (await client.post(path,json={})).status_code == 404
    settings.enabled = True
    assert (await client.post(path,json={})).status_code == 403
    headers = {"X-Setup-Token":settings.token.get_secret_value()}
    first = await client.post(path,json={},headers=headers)
    assert first.status_code == 200, first.text
    initialized = first.json()
    assert initialized["table_count"] == 11 and initialized["sources_added"] == 3
    assert initialized["active_rule_version_id"] == initialized["bundled_rule_version_id"]
    assert initialized["active_revision"] == 1
    again = await client.post(path,json={},headers=headers)
    assert again.status_code == 200,again.text
    assert again.json()["sources_added"] == 0 and again.json()["active_revision"] == 1
    assert again.json()["active_rule_preserved"]
    async with service.sessions() as session:
        from sqlalchemy import func
        assert await session.scalar(select(func.count()).select_from(RuleVersion)) == 1
        assert await session.scalar(select(func.count()).select_from(RulePublication)) == 1
        assert await session.scalar(select(func.count()).select_from(RuleValidationTask)) == 0
        assert await session.scalar(select(func.count()).select_from(RulePDFReport)) == 0
    assert (await client.post(path,json={"sql":"DROP"},headers=headers)).status_code == 422


async def test_initialization_preserves_active_rules_and_existing_sources(task_api, tmp_path):
    _, task_service, _ = task_api
    database = task_service.repository.sessions.kw["bind"]
    initialization = InitializationService(database, task_service.repository.sessions,tmp_path / "existing.lock")
    # Test fixture was created with metadata, not Alembic: intentionally refuse to stamp it.
    with pytest.raises(AppException) as conflict:
        await initialization.initialize()
    assert conflict.value.code == "SETUP_SCHEMA_CONFLICT"


async def test_initialization_seeds_real_worker_flow(empty_setup):
    client, setup, settings = empty_setup
    settings.enabled = True
    await client.post("/api/v1/rule-engine/setup/initialize",json={},headers={"X-Setup-Token":settings.token.get_secret_value()})
    from cryptography.fernet import Fernet
    from backend.core.rule_tasks import RuleTaskSettings
    from backend.engine.rule_loader import RuleLoader
    from backend.engine.validation import ValidationEngine
    from backend.services.rule_api import RuleAPIService
    from backend.services.rule_tasks import TaskService,get_task_service
    from backend.services.pdf_reports import PDFReportService,get_pdf_report_service
    from backend.workers.rule_tasks import RuleTaskWorker
    from backend.workers.pdf_reports import PDFReportWorker
    task_service = TaskService(RuleAPIService(ValidationEngine(RuleLoader(setup.sessions))),RuleTaskSettings(_env_file=None,encryption_keys=[SecretStr(Fernet.generate_key().decode())]))
    client._transport.app.dependency_overrides[get_task_service]=lambda:task_service
    client._transport.app.dependency_overrides[get_pdf_report_service]=lambda:PDFReportService(task_service)
    submitted = await task_fixtures.submit(client)
    assert await RuleTaskWorker(task_service).run_once()
    assert await PDFReportWorker(task_service).run_once()
    response = await client.get(submitted.headers["Location"])
    assert response.json()["report_status"] == "READY"
    assert (await client.get(response.json()["report_url"])).content.startswith(b"%PDF-")


async def test_initializer_preserves_non_default_active_version_and_disabled_sources(empty_setup):
    from backend.engine.publication import RulePublisher
    _, setup, _ = empty_setup
    await setup.initialize()
    rules = json.loads(Path("rules/rules_global_v4.json").read_text())
    first_country = next(iter(rules["jurisdictions"]))
    rules["jurisdictions"][first_country][0]["source_section"] += " (isolated preservation fixture)"
    publisher = RulePublisher(setup.sessions)
    alternate = await publisher.register(rules, [])
    await publisher.approve(alternate, {"review":"test only"})
    await publisher.activate(alternate, 1)
    async with setup.sessions.begin() as session:
        source = await session.scalar(select(RuleSource))
        source.enabled, source.name = False, "Existing source kept"
        source_id = source.id
    result = await setup.initialize()
    assert result.active_rule_preserved and result.active_rule_version_id == alternate and result.active_revision == 2
    async with setup.sessions() as session:
        source = await session.get(RuleSource, source_id)
        assert not source.enabled and source.name == "Existing source kept"


async def test_initializer_rejects_partial_or_incompatible_schema(empty_setup):
    from backend.models import Base
    _, setup, _ = empty_setup
    async with setup.database.begin() as connection:
        schema = await connection.run_sync(lambda c:c.get_execution_options()["schema_translate_map"]["crosstax"])
        if schema:
            from sqlalchemy.schema import CreateSchema
            await connection.execute(CreateSchema(schema))
        await connection.run_sync(lambda c: Base.metadata.tables["crosstax.rule_sources"].create(c))
    with pytest.raises(AppException) as error:
        await setup.initialize()
    assert error.value.code == "SETUP_SCHEMA_CONFLICT"
    async with setup.database.connect() as connection:
        assert await connection.run_sync(lambda c:inspect(c).get_table_names(schema=c.get_execution_options()["schema_translate_map"]["crosstax"])) == ["rule_sources"]


async def test_initializer_lock_and_short_token(empty_setup):
    from backend.infrastructure.job_lock import job_lock
    client, setup, settings = empty_setup
    settings.enabled, settings.token = True, SecretStr("short")
    response = await client.post("/api/v1/rule-engine/setup/initialize",json={},headers={"X-Setup-Token":"short"})
    assert response.status_code == 503 and response.json()["code"] == "SETUP_NOT_CONFIGURED"
    with job_lock(setup.lock_path) as acquired:
        assert acquired
        with pytest.raises(AppException) as busy:
            await setup.initialize()
        assert busy.value.code == "SETUP_BUSY"


async def test_comparison_expiry_and_bounded_diffs(task_api):
    from datetime import timedelta
    from backend.infrastructure.rule_tasks import utcnow
    client, service, worker = task_api
    request = task_fixtures.payload()
    _, before = await finish(client, worker, request)
    new_url, after = await finish(client, worker, request)
    first, second = await service.get(before["task_id"]), await service.get(after["task_id"])
    comparison = compare_tasks(first,second,{"fields":["a"]*300},{"fields":["b"]*300})
    assert comparison.changed_field_count == 300 and len(comparison.changed_fields)==200 and comparison.changed_fields_truncated
    async with service.repository.sessions.begin() as session:
        old = await session.get(RuleValidationTask,before["task_id"])
        old.expires_at = utcnow() - timedelta(seconds=1)
    assert (await client.get(new_url,params={"compare_to":before["task_id"]})).status_code == 410


def test_internal_routes_hidden_unless_demo_explicitly_enabled(monkeypatch):
    paths = create_app().openapi()["paths"]
    assert not any("setup" in path or "demo" in path for path in paths)
    monkeypatch.setattr("backend.main.get_demo_settings", lambda:DemoSettings(_env_file=None,enabled=True))
    paths = create_app().openapi()["paths"]
    assert "/api/v1/rule-engine/demo/upgrade-impact" in paths
    assert not any("setup" in path for path in paths)


async def test_initialization_keeps_teammate_business_table(empty_setup):
    from sqlalchemy import MetaData, insert
    from sqlalchemy.schema import CreateSchema
    from backend.models.user import User
    _, setup, _ = empty_setup
    table = User.__table__.to_metadata(MetaData(), schema="crosstax")
    async with setup.database.begin() as connection:
        schema = await connection.run_sync(lambda c:c.get_execution_options()["schema_translate_map"]["crosstax"])
        if schema:
            await connection.execute(CreateSchema(schema))
        await connection.run_sync(lambda c:table.create(c))
        await connection.execute(insert(table).values(id=1, username="teammate-fixture", email="fixture@example.invalid"))
    await setup.initialize()
    async with setup.database.connect() as connection:
        assert await connection.scalar(select(table.c.username)) == "teammate-fixture"


async def test_unknown_execution_context_is_not_presented_as_a_clean_correction(task_api):
    client, service, worker = task_api
    request = task_fixtures.payload()
    _, first = await finish(client, worker, request)
    _, second = await finish(client, worker, request)
    before, after = await service.get(first["task_id"]), await service.get(second["task_id"])
    before.result.execution = None
    summary = compare_tasks(before, after, request["validation"], request["validation"])
    assert summary.context == "DIFFERENT_CONTEXT" and "EXECUTION_CONTEXT_MISSING" in summary.context_changes


async def test_initializer_upgrades_complete_legacy_baseline_without_stamping(empty_setup):
    from backend.models import Base
    from backend.infrastructure.schema_setup import BASE_TABLES
    from sqlalchemy.schema import CreateSchema
    _, setup, _ = empty_setup
    async with setup.database.begin() as connection:
        schema = await connection.run_sync(lambda c:c.get_execution_options()["schema_translate_map"]["crosstax"])
        if schema:
            await connection.execute(CreateSchema(schema))
        tables = [table for table in Base.metadata.sorted_tables if table.schema == "crosstax" and table.name in BASE_TABLES]
        await connection.run_sync(lambda c:Base.metadata.create_all(c,tables=tables))
    async with setup.sessions.begin() as session:
        session.add(RuleEngineState(id=1))
    result = await setup.initialize()
    assert result.table_count == 11 and result.active_revision == 1 and result.sources_added == 3
    again = await setup.initialize()
    assert again.active_revision == 1 and again.active_rule_preserved
