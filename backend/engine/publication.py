"""Validated rule registration and explicit version activation."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.engine.regression import run_regressions
from backend.engine.reproducibility import canonical_hash, engine_build_id
from backend.engine.rule_loader import compile_snapshot
from backend.infrastructure.exceptions import ConflictException
from backend.repositories.rules import RuleRepository


class RulePublisher:
    """A caller must approve domain semantics before requesting publication."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions

    async def register(self, rules: dict[str, object], document_ids: list[str]) -> str:
        compile_snapshot(canonical_hash(rules), 0, rules)
        for attempt in range(2):
            try:
                async with self.sessions.begin() as session:
                    repository = RuleRepository(session)
                    version = await repository.create_candidate(
                        rules, document_ids, {"origin": "structured_rule_input"}
                    )
                    compile_snapshot(version.version_id, 0, version.rules)
                    version.schema_version = 2 if rules.get("schema_version") == 2 else 1
                    return version.version_id
            except IntegrityError:
                if attempt:
                    raise
        raise RuntimeError("Unreachable registration state")

    async def approve(self, version_id: str, report: dict[str, object]) -> None:
        async with self.sessions.begin() as session:
            from backend.models import RuleVersion

            version = await session.get(RuleVersion, version_id)
            if version is None:
                raise ValueError("Unknown rule version")
            snapshot = compile_snapshot(version.version_id, 0, version.rules)
            gate = run_regressions(snapshot, report.get("regression_cases"))
            gate["engine_build_id"] = engine_build_id()
            await RuleRepository(session).review_candidate(version_id, True, {"review": report, "regression": gate})

    async def activate(
        self, version_id: str, expected_revision: int, *, actor: str = "local", reason: str = "manual activation"
    ) -> None:
        async with self.sessions.begin() as session:
            from backend.models import RuleVersion

            version = await session.get(RuleVersion, version_id)
            if version is None:
                raise ValueError("Unknown rule version")
            if version.status != "APPROVED":
                raise ConflictException("Only approved versions can be activated")
            snapshot = compile_snapshot(version.version_id, expected_revision + 1, version.rules)
            review = version.validation_report.get("review", {})
            cases = review.get("regression_cases") if isinstance(review, dict) else None
            run_regressions(snapshot, cases)
            from backend.models import RuleEngineState, RulePublication

            state = await session.get(RuleEngineState, 1)
            previous = state.active_version_id if state else None
            if not actor.strip() or len(actor) > 200 or not reason.strip() or len(reason) > 2000:
                raise ValueError("Publication actor/reason is missing or oversized")
            await RuleRepository(session).activate(version_id, expected_revision)
            session.add(
                RulePublication(
                    revision=expected_revision + 1,
                    version_id=version_id,
                    previous_version_id=previous,
                    actor=actor,
                    reason=reason,
                )
            )
