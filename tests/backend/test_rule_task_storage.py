"""Encrypted persistence, admission, leases and portable migration behavior."""

import importlib.util
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.core.rule_tasks import RuleTaskSettings, TaskCipher
from backend.infrastructure.exceptions import AppException
from backend.infrastructure.rule_tasks import TaskRepository, utcnow
from backend.models import Base, RuleValidationTask, RuleVersion


@pytest.fixture
async def repository(tmp_path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'tasks.db'}",
        execution_options={"schema_translate_map": {"crosstax": None}},
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions.begin() as session:
        session.add(RuleVersion(version_id="a" * 64, rules={}, validation_report={}, extraction_metadata={}))
    yield TaskRepository(sessions, RuleTaskSettings(_env_file=None, capacity=1))
    await engine.dispose()


def task(key="test-key"):
    now = utcnow()
    return RuleValidationTask(
        task_id=str(uuid4()), session_id=str(uuid4()), idempotency_key=key, request_digest="b" * 64,
        status="PENDING", rule_version_id="a" * 64, rule_revision=1, engine_build_id="c" * 64,
        payload_ciphertext="encrypted", attempts=0, created_at=now, deadline_at=now + timedelta(seconds=30),
        expires_at=now + timedelta(days=1),
    )


def test_authenticated_cipher_rotation_and_keyed_digest():
    old, new = SecretStr(Fernet.generate_key().decode()), SecretStr(Fernet.generate_key().decode())
    original = TaskCipher([old])
    rotated = TaskCipher([new, old])
    value = {"tin": "synthetic-sensitive-marker"}
    encrypted = original.encrypt(value)
    assert value["tin"] not in encrypted
    assert rotated.decrypt(encrypted) == value
    assert original.digests(value)[0] in rotated.digests(value)
    assert original.digests(value)[0] != rotated.digests(value)[0]
    with pytest.raises(Exception):
        rotated.decrypt(encrypted[:-4] + "AAAA")
    with pytest.raises(ValueError):
        TaskCipher([])


async def test_admission_duplicate_capacity_and_atomic_result(repository):
    first = await repository.enqueue(task())
    assert (await repository.enqueue(task())).task_id == first.task_id
    with pytest.raises(AppException) as caught:
        await repository.enqueue(task("second"))
    assert caught.value.status_code == 503
    claim = await repository.claim()
    assert claim.task_id == first.task_id and claim.attempts == 1
    assert not await repository.finish(first.task_id, "stale", "wrong")
    assert await repository.renew(first.task_id, claim.claim_token)
    assert await repository.finish(first.task_id, claim.claim_token, "cipher-result")
    saved = await repository.get(first.task_id)
    assert saved.status == "SUCCEEDED" and saved.result_ciphertext == "cipher-result"
    assert not await repository.finish(first.task_id, claim.claim_token, None, "OLD_FAILURE")
    assert (await repository.enqueue(task("second"))).status == "PENDING"


async def test_expired_lease_is_reclaimed_and_old_owner_fenced(repository):
    first = await repository.enqueue(task())
    old = await repository.claim()
    async with repository.sessions.begin() as session:
        row = await session.get(RuleValidationTask, first.task_id)
        row.lease_until = utcnow() - timedelta(seconds=1)
    new = await repository.claim()
    assert new.attempts == 2 and new.claim_token != old.claim_token
    assert not await repository.renew(first.task_id, old.claim_token)
    assert not await repository.finish(first.task_id, old.claim_token, "old")
    assert await repository.finish(first.task_id, new.claim_token, "new")


async def test_deadline_attempt_limit_and_retention_tombstone(repository):
    first = task()
    first.deadline_at = utcnow() - timedelta(seconds=1)
    await repository.enqueue(first)
    assert await repository.claim() is None
    assert (await repository.get(first.task_id)).status == "FAILED"
    async with repository.sessions.begin() as session:
        row = await session.get(RuleValidationTask, first.task_id)
        row.expires_at = utcnow() - timedelta(seconds=1)
    assert await repository.cleanup() == 1
    saved = await repository.by_key(first.idempotency_key)
    assert saved.task_id == first.task_id and saved.payload_ciphertext is None
    assert await repository.cleanup() == 0
    second = task("second")
    second.attempts = repository.settings.max_attempts
    await repository.enqueue(second)
    assert await repository.claim() is None
    assert (await repository.get(second.task_id)).status == "FAILED"


def test_autogenerated_task_migration_round_trip():
    path = next(Path("alembic/versions").glob("20261108_rule_tasks*.py"))
    spec = importlib.util.spec_from_file_location("task_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = create_engine("sqlite://", execution_options={"schema_translate_map": {"crosstax": None}})
    with engine.begin() as connection:
        baseline = [t for t in Base.metadata.sorted_tables if t.name not in
                    {"rule_validation_tasks", "rule_task_queue_state"}]
        Base.metadata.create_all(connection, tables=baseline)
        module.op = Operations(MigrationContext.configure(connection))
        module.upgrade()
        assert "rule_validation_tasks" in inspect(connection).get_table_names()
        connection.execute(select(RuleValidationTask))
        module.downgrade()
        assert "rule_validation_tasks" not in inspect(connection).get_table_names()
    engine.dispose()


def test_alembic_cli_uses_sqlite_schema_translation(tmp_path):
    import os
    import subprocess
    import sys

    database = tmp_path / "migration.db"
    engine = create_engine(f"sqlite:///{database}", execution_options={"schema_translate_map": {"crosstax": None}})
    with engine.begin() as connection:
        Base.metadata.create_all(connection, tables=[t for t in Base.metadata.sorted_tables if t.name not in
                                 {"rule_validation_tasks", "rule_task_queue_state"}])
    env = os.environ | {"DATABASE_URL": f"sqlite+aiosqlite:///{database}"}
    for args in (("stamp", "20261103_rule_history"), ("upgrade", "head"),
                 ("downgrade", "20261103_rule_history")):
        subprocess.run([sys.executable, "-m", "alembic", *args], env=env, check=True, capture_output=True)
        with engine.connect() as connection:
            assert ("rule_validation_tasks" in inspect(connection).get_table_names()) == (args[0] == "upgrade")
    engine.dispose()


async def test_concurrent_queue_admission_and_claim_are_bounded(repository):
    import asyncio

    results = await asyncio.gather(repository.enqueue(task("first")), repository.enqueue(task("second")),
                                   return_exceptions=True)
    assert sum(isinstance(result, RuleValidationTask) for result in results) == 1
    assert sum(isinstance(result, AppException) and result.status_code == 503 for result in results) == 1
    claimed = await asyncio.gather(repository.claim(), repository.claim())
    assert sum(result is not None for result in claimed) == 1
