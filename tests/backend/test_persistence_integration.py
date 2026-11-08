"""Same persistence lifecycle on SQLite and an optional isolated PostgreSQL schema."""

import asyncio
import json
import os
import runpy
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateSchema, DropSchema

from backend.engine.audit_service import AuditValidationService
from backend.engine.contracts import CRSFormData, ValidationPolicy
from backend.engine.publication import RulePublisher
from backend.engine.rule_loader import RuleLoader
from backend.engine.validation import ValidationEngine
from backend.infrastructure.exceptions import ConflictException
from backend.models import Base, RuleAuditRecord, RuleEngineState, RulePublication, RuleVersion


@pytest.fixture(params=["sqlite", "postgresql"])
async def persistence(request):
    pg = request.param == "postgresql"
    url = os.getenv("CROSSTAX_TEST_DATABASE_URL") if pg else "sqlite+aiosqlite://"
    if not url:
        pytest.skip("Set CROSSTAX_TEST_DATABASE_URL for isolated PostgreSQL integration")
    schema = "crosstax_test_" + uuid4().hex if pg else None
    engine = create_async_engine(url, execution_options={"schema_translate_map": {"crosstax": schema}})
    tables = [table for table in Base.metadata.sorted_tables if table.schema == "crosstax"]
    try:
        async with engine.begin() as conn:
            if pg:
                await conn.execute(CreateSchema(schema))
            await conn.run_sync(
                lambda c: Base.metadata.create_all(
                    c, tables=[t for t in tables if t.name not in {"rule_publications", "rule_audit_records", "rule_validation_tasks", "rule_task_queue_state", "rule_pdf_reports"}]
                )
            )

            def migrate(connection):
                from alembic.migration import MigrationContext
                from alembic.operations import Operations

                migration = runpy.run_path("alembic/versions/20261103_rule_history.py")
                with Operations.context(MigrationContext.configure(connection)):
                    migration["upgrade"]()
                    tasks = runpy.run_path(str(next(Path("alembic/versions").glob("20261108_rule_tasks*.py"))))
                    tasks["upgrade"]()
                    reports = runpy.run_path(str(next(Path("alembic/versions").glob("20261108_pdf_reports*.py"))))
                    reports["upgrade"]()

            await conn.run_sync(migrate)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions.begin() as session:
            session.add(RuleEngineState(id=1))
        yield sessions, pg
    finally:
        if pg:
            async with engine.begin() as conn:
                await conn.execute(DropSchema(schema, cascade=True))
        await engine.dispose()


def report(value):
    return {
        "regression_cases": [
            {"case_id": "valid", "jurisdiction_code": "HK", "tin": value, "valid": True},
            {"case_id": "invalid", "jurisdiction_code": "HK", "tin": "!", "valid": False},
        ]
    }


async def published(sessions, length=8):
    publisher = RulePublisher(sessions)
    version = await publisher.register({"HK": {"regex": f"[0-9]{{{length}}}", "algorithm": "REGEX_ONLY"}}, [])
    await publisher.approve(version, report("1" * length))
    return publisher, version


async def test_handoff_persists_replays_and_retries_original_result(persistence):
    sessions, _ = persistence
    publisher, version = await published(sessions)
    await publisher.activate(version, 0, actor="integration-test", reason="initial publication")
    base = json.loads(Path("assets/mock-data/cases.json").read_text())[0]["form_data"]
    form = CRSFormData.model_validate(base | {"jurisdiction_code": "HK", "tin": "12345678"})
    policy = ValidationPolicy.model_validate({"today": "2026-11-03"})
    service = AuditValidationService(ValidationEngine(RuleLoader(sessions)))
    result = await service.validate_and_store("demo-session", form, policy)
    assert await service.replay_stored("demo-session") == result
    _, second = await published(sessions, 9)
    await publisher.activate(second, 1)
    assert await service.validate_and_store("demo-session", form, policy) == result
    with pytest.raises(ConflictException):
        await service.validate_and_store("demo-session", form.model_copy(update={"tin": "87654321"}), policy)
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(RuleAuditRecord)) == 1
        history = list((await session.scalars(select(RulePublication).order_by(RulePublication.revision))).all())
        assert len(history) == 2 and history[1].previous_version_id == version


async def test_publication_cas_and_duplicate_registration(persistence):
    sessions, pg = persistence
    publisher, version = await published(sessions)
    if pg:
        results = await asyncio.gather(
            publisher.activate(version, 0), publisher.activate(version, 0), return_exceptions=True
        )
        assert sum(result is None for result in results) == 1
        assert sum(isinstance(result, ConflictException) for result in results) == 1
        versions = await asyncio.gather(
            *[publisher.register({"HK": {"regex": "[0-9]{9}", "algorithm": "REGEX_ONLY"}}, []) for _ in range(2)]
        )
        assert versions[0] == versions[1]
    else:
        await publisher.activate(version, 0)
        with pytest.raises(ConflictException):
            await publisher.activate(version, 0)
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(RulePublication)) == 1


async def test_false_report_and_mutation_do_not_commit(persistence):
    sessions, _ = persistence
    publisher = RulePublisher(sessions)
    candidate = await publisher.register({"HK": {"regex": "[0-9]{8}", "algorithm": "REGEX_ONLY"}}, [])
    with pytest.raises(ValueError, match="Regression gate"):
        await publisher.approve(candidate, {"passed": True})
    async with sessions() as session:
        assert (await session.get(RuleVersion, candidate)).status == "CANDIDATE"
    await publisher.approve(candidate, report("12345678"))
    with pytest.raises(ValueError, match="candidate transition"):
        async with sessions.begin() as session:
            await session.execute(
                update(RuleVersion).where(RuleVersion.version_id == candidate).values(status="CANDIDATE")
            )
    with pytest.raises(ValueError, match="immutable"):
        async with sessions.begin() as session:
            record = await session.get(RuleVersion, candidate)
            record.rules = {"HK": {"regex": "[0-9]{9}", "algorithm": "REGEX_ONLY"}}
    async with sessions() as session:
        assert (await session.get(RuleVersion, candidate)).rules["HK"]["regex"] == "[0-9]{8}"


async def test_encrypted_tasks_use_migrated_tables_on_both_backends(persistence):
    from cryptography.fernet import Fernet
    from pydantic import SecretStr
    from backend.api.schemas.rule_tasks import TaskRequest
    from backend.core.rule_tasks import RuleTaskSettings
    from backend.services.rule_api import RuleAPIService
    from backend.services.rule_tasks import TaskService
    from backend.workers.rule_tasks import RuleTaskWorker

    sessions, _ = persistence
    publisher, version = await published(sessions)
    await publisher.activate(version, 0)
    base = json.loads(Path("assets/mock-data/cases.json").read_text())[0]["form_data"]
    request = TaskRequest.model_validate({
        "session_id": str(uuid4()), "validation": {
            "form_data": base | {"jurisdiction_code": "HK", "tin": "12345678"},
            "policy": {"today": "2026-11-03"},
        },
    })
    service = TaskService(RuleAPIService(ValidationEngine(RuleLoader(sessions))), RuleTaskSettings(
        _env_file=None, encryption_keys=[SecretStr(Fernet.generate_key().decode())]))
    task = await service.submit(request, str(uuid4()))
    assert task.status == "PENDING"
    assert await RuleTaskWorker(service).run_once()
    complete = await service.get(str(task.task_id))
    assert complete.status == "SUCCEEDED" and complete.result.verdict == "AUTO_PASS"
    from backend.services.pdf_reports import PDFReportService
    from backend.workers.pdf_reports import PDFReportWorker
    await PDFReportWorker(service).run_once()
    report = await PDFReportService(service).export(str(task.task_id))
    assert report.content.startswith(b"%PDF-") and report.filename.endswith(".pdf")
