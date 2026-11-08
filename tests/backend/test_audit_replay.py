"""Replay uses historical rules and rejects changed execution inputs/builds."""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.engine.contracts import CRSFormData
from backend.engine.publication import RulePublisher
from backend.engine.rule_loader import RuleLoader
from backend.engine.validation import ValidationEngine
from backend.models import Base, RuleEngineState
from tests.backend.test_audit_completeness import BASE, POLICY


async def test_historical_replay_after_publication_and_tamper_rejection():
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
        first = await publisher.register({"CN": {"regex": "[0-9]{17}[0-9X]", "algorithm": "MOD11_2"}}, [])
        await publisher.approve(first, report("CN", "11010519491231002X"))
        await publisher.activate(first, 0)
        engine = ValidationEngine(RuleLoader(sessions))
        form = CRSFormData.model_validate(BASE)
        original = await engine.validate(form, POLICY)
        second = await publisher.register({"CN": {"regex": "[0-9]{18}", "algorithm": "REGEX_ONLY"}}, [])
        await publisher.approve(second, report("CN", "1" * 18))
        await publisher.activate(second, 1)
        assert (await engine.validate(form, POLICY)).verdict == "NEED_USER_FIX"
        assert await engine.replay(form, original) == original
        assert engine.loader.current().version_id == second
        with pytest.raises(ValueError, match="input"):
            await engine.replay(CRSFormData.model_validate(BASE | {"holder_name": "Changed"}), original)
        wrong_build = original.model_copy(
            update={"execution": original.execution.model_copy(update={"engine_build_id": "wrong"})}
        )
        with pytest.raises(ValueError, match="build"):
            await engine.replay(form, wrong_build)
        wrong_result = original.model_copy(update={"verdict": "MANUAL_TRIAGE"})
        with pytest.raises(ValueError, match="differs"):
            await engine.replay(form, wrong_result)
    finally:
        await database.dispose()


def report(code, value):
    return {
        "regression_cases": [
            {"case_id": "positive", "jurisdiction_code": code, "tin": value, "valid": True},
            {"case_id": "negative", "jurisdiction_code": code, "tin": "!", "valid": False},
        ]
    }
