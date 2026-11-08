"""Publication validates candidates before committing and supports rollback."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.engine.publication import RulePublisher
from backend.engine.rule_loader import RuleLoader
from backend.infrastructure.exceptions import ConflictException
from backend.models import Base, RuleEngineState, RuleVersion


async def test_publication_transactions():
    engine = create_async_engine("sqlite+aiosqlite://", execution_options={"schema_translate_map": {"crosstax": None}})
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions.begin() as session:
            session.add(RuleEngineState(id=1))
        publisher = RulePublisher(sessions)
        with pytest.raises(ValueError):
            await publisher.register({}, [])
        async with sessions() as session:
            assert await session.scalar(select(func.count()).select_from(RuleVersion)) == 0
        first = await publisher.register({"HK": {"regex": "[0-9]{8}", "algorithm": "REGEX_ONLY"}}, [])
        with pytest.raises(ConflictException):
            await publisher.activate(first, 0)
        await publisher.approve(first, report("HK", "12345678"))
        await publisher.activate(first, 0)
        second = await publisher.register({"HK": {"regex": "[0-9]{9}", "algorithm": "REGEX_ONLY"}}, [])
        await publisher.approve(second, report("HK", "123456789"))
        await publisher.activate(second, 1)
        await publisher.activate(first, 2)
        snapshot = await RuleLoader(sessions).refresh()
        assert snapshot.version_id == first
        assert snapshot.revision == 3
    finally:
        await engine.dispose()


def report(code, value):
    return {
        "regression_cases": [
            {"case_id": "positive", "jurisdiction_code": code, "tin": value, "valid": True},
            {"case_id": "negative", "jurisdiction_code": code, "tin": "!", "valid": False},
        ]
    }
