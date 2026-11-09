"""Read-only simulation and non-destructive initialization of bundled project data."""

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import cast

import httpx
from pydantic import TypeAdapter
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from backend.api.schemas.competition import InitializationResult, UpgradeDemo
from backend.engine.contracts import ValidationPolicy
from backend.engine.impact import analyze_impact
from backend.engine.publication import RulePublisher
from backend.engine.reproducibility import canonical_hash
from backend.engine.rule_loader import RuleLoader, compile_snapshot
from backend.engine.validation import ValidationEngine
from backend.infrastructure.database import async_session_factory, engine
from backend.infrastructure.exceptions import AppException
from backend.infrastructure.job_lock import job_lock
from backend.infrastructure.schema_setup import ROOT, SchemaConflict, upgrade_rule_schema
from backend.models import RuleEngineState, RuleTaskQueueState, RuleVersion
from backend.services.rule_import import RuleSourceImporter, SourceDefinition


@lru_cache(maxsize=1)
def upgrade_demo() -> UpgradeDemo:
    from backend.cli.demo_cases import snapshot

    base = snapshot(json.loads((ROOT / "rules/rules_v1_base.json").read_text(encoding="utf-8")), 1)
    candidate = snapshot(json.loads((ROOT / "rules/rules_v2_patch.json").read_text(encoding="utf-8")), 2)
    cases = json.loads((ROOT / "assets/mock-data/cases.json").read_text(encoding="utf-8"))
    report = analyze_impact(
        ValidationEngine(RuleLoader(async_session_factory)),
        base,
        candidate,
        cases,
        ValidationPolicy.model_validate({"today": "2026-11-02"}),
    )
    return UpgradeDemo(impact=report)


class InitializationService:
    def __init__(
        self, database: AsyncEngine, sessions: async_sessionmaker[AsyncSession], lock_path: Path | None = None
    ) -> None:
        self.database, self.sessions = database, sessions
        url = database.url
        identity = str((url.drivername, url.host, url.port, url.database))
        self.lock_path = lock_path or ROOT / "outputs" / (
            "initialize-" + hashlib.sha256(identity.encode()).hexdigest()[:16] + ".lock"
        )

    async def initialize(self) -> InitializationResult:
        try:
            with job_lock(self.lock_path) as acquired:
                if not acquired:
                    raise AppException(409, "SETUP_BUSY", "Initialization is already running")
                async with self.database.begin() as connection:
                    revision, count = await connection.run_sync(upgrade_rule_schema)
                # Repeatable seed phases: never overwrite an existing source or active version.
                async with self.sessions.begin() as session:
                    state = await session.get(RuleEngineState, 1)
                    preserved = state is not None and state.active_version_id is not None
                    if preserved and state is not None:
                        active = await session.get(RuleVersion, state.active_version_id)
                        if active is None or active.status != "APPROVED":
                            raise AppException(409, "SETUP_ACTIVE_INVALID", "Existing active rule is not approved")
                    if state is None:
                        session.add(RuleEngineState(id=1))
                    if await session.get(RuleTaskQueueState, 1) is None:
                        session.add(RuleTaskQueueState(id=1, generation=0))
                definitions = TypeAdapter(list[SourceDefinition]).validate_json(
                    (ROOT / "assets/rule-sources/oecd.json").read_text(encoding="utf-8")
                )
                async with httpx.AsyncClient() as client:
                    added = await RuleSourceImporter(self.sessions, client).register(definitions)
                rules = cast(
                    dict[str, object],
                    json.loads((ROOT / "rules/rules_global_v4.json").read_text(encoding="utf-8")),
                )
                compile_snapshot(canonical_hash(rules), 0, rules)
                publisher = RulePublisher(self.sessions)
                version_id = await publisher.register(rules, [])
                async with self.sessions() as session:
                    version = await session.get(RuleVersion, version_id)
                    status = version.status if version else None
                if status == "REJECTED":
                    raise AppException(
                        409, "SETUP_RULE_REJECTED", "Bundled rule version was rejected; no override performed"
                    )
                if status == "CANDIDATE":
                    await publisher.approve(
                        version_id, {"source": "reviewed repository bootstrap", "live_refresh": False}
                    )
                async with self.sessions() as session:
                    state = await session.get(RuleEngineState, 1)
                    assert state is not None
                    activate = state.active_version_id is None
                    expected_revision = state.revision
                if activate:
                    await publisher.activate(
                        version_id, expected_revision, actor="initialization", reason="initial bundled rules"
                    )
                async with self.sessions() as session:
                    state = await session.get(RuleEngineState, 1)
                    assert state is not None
                    return InitializationResult(
                        migration_revision=revision,
                        table_count=count,
                        sources_added=added,
                        bundled_rule_version_id=version_id,
                        active_rule_version_id=state.active_version_id,
                        active_revision=state.revision,
                        active_rule_preserved=preserved,
                        next_steps=[
                            "配置共享 RULE_TASK_ENCRYPTION_KEYS",
                            "启动现有双循环 Worker",
                            "关闭 RULE_SETUP_ENABLED",
                        ],
                    )
        except SchemaConflict as exc:
            raise AppException(
                409, "SETUP_SCHEMA_CONFLICT", "Existing schema requires explicit reconciliation"
            ) from exc
        except AppException:
            raise
        except Exception as exc:
            raise AppException(
                503, "SETUP_FAILED", "Initialization could not complete; check database and bundled configuration"
            ) from exc


@lru_cache(maxsize=1)
def get_initialization_service() -> InitializationService:
    return InitializationService(engine, async_session_factory)
