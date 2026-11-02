"""Validated rule registration and explicit version activation."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.engine.rule_loader import compile_snapshot
from backend.repositories.rules import RuleRepository


class RulePublisher:
    """A caller must approve domain semantics before requesting publication."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions

    async def register(self, rules: dict[str, object], document_ids: list[str]) -> str:
        async with self.sessions.begin() as session:
            repository = RuleRepository(session)
            version = await repository.create_candidate(rules, document_ids, {"origin": "structured_rule_input"})
            compile_snapshot(version.version_id, 0, version.rules)
            return version.version_id

    async def approve(self, version_id: str, report: dict[str, object]) -> None:
        async with self.sessions.begin() as session:
            from backend.models import RuleVersion

            version = await session.get(RuleVersion, version_id)
            if version is None:
                raise ValueError("Unknown rule version")
            compile_snapshot(version.version_id, 0, version.rules)
            await RuleRepository(session).review_candidate(version_id, True, report)

    async def activate(self, version_id: str, expected_revision: int) -> None:
        async with self.sessions.begin() as session:
            from backend.models import RuleVersion

            version = await session.get(RuleVersion, version_id)
            if version is None:
                raise ValueError("Unknown rule version")
            compile_snapshot(version.version_id, expected_revision + 1, version.rules)
            await RuleRepository(session).activate(version_id, expected_revision)
