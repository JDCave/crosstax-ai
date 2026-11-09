"""Controlled background promotion on an isolated SQLite database."""

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.engine.contracts import ValidationPolicy
from backend.engine.publication import RulePublisher
from backend.engine.reproducibility import canonical_hash
from backend.infrastructure.exceptions import ConflictException
from backend.models import Base, RuleEngineState, RulePublication, RuleSyncRun, RuleVersion
from backend.repositories.rules import RuleRepository
from backend.services.rule_updates import PublicationPolicy, RuleBundle, RuleUpdateCoordinator

SOURCE = "https://www.oecd.org/content/dam/oecd/en/topics/policy-issue-focus/aeoi/hong-kong-tin.pdf"


def regressions(positive="A1234563"):
    return [
        dict(case_id=name, jurisdiction_code="HK", holder_type="INDIVIDUAL", tin_type="HKID", tin=tin, valid=valid)
        for name, tin, valid in [("positive", positive, True), ("negative", "!", False)]
    ]


@pytest.fixture
async def context():
    db = create_async_engine("sqlite+aiosqlite://", execution_options={"schema_translate_map": {"crosstax": None}})
    async with db.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(db, expire_on_commit=False)
    rules = {
        "schema_version": 2,
        "jurisdictions": {
            "HK": [
                {
                    "rule_id": "HK_DEMO",
                    "holder_type": "INDIVIDUAL",
                    "tin_type": "HKID",
                    "regex": "[A-Z][0-9]{6}[0-9A]",
                    "algorithm": "REGEX_ONLY",
                    "verification_level": "FORMAT_ONLY",
                    "source_url": SOURCE,
                    "source_section": "II",
                }
            ]
        },
    }
    async with sessions.begin() as session:
        session.add(RuleEngineState(id=1))
        repo = RuleRepository(session)
        source = await repo.add_source("Synthetic official-source fixture", "HK", SOURCE)
        source.last_checked_at = datetime.now(UTC)
        run = await repo.start_sync()
        document = await repo.store_document(source.id, run.id, b"%PDF-1.7 synthetic test evidence", "application/pdf")
        await repo.finish_sync(run.id, "SUCCEEDED", {})
    publisher = RulePublisher(sessions)
    base = await publisher.register(rules, [document.id])
    await publisher.approve(base, {"regression_cases": regressions()})
    await publisher.activate(base, 0)
    candidate = json.loads(json.dumps(rules))
    candidate["jurisdictions"]["HK"][0]["regex"] = "[A-Z]{1,2}[0-9]{6}[0-9A]"
    bundle = RuleBundle(
        schema_version=1,
        base_version_id=base,
        rules=candidate,
        documents=[{"document_id": document.id, "content_hash": document.content_hash}],
        regression_cases=regressions(),
    )
    request = json.loads(Path("assets/crs-templates/crs-individual-request.json").read_text(encoding="utf-8"))
    cases = [{"case_id": "SAFE_CASE", "form_data": request["form_data"]}]
    policy = ValidationPolicy.model_validate(request["policy"])
    try:
        yield sessions, publisher, bundle, cases, policy, source.id
    finally:
        await db.dispose()


def trust(result):
    return PublicationPolicy(
        schema_version=1,
        approvals=[
            {
                "base_version_id": result.base_version_id,
                "candidate_version_id": result.candidate_version_id,
                "impact_hash": result.impact.report_hash,
                "evidence_hash": result.evidence_hash,
            }
        ],
    )


async def test_plan_approve_trust_publish_and_idempotent_rerun(context):
    sessions, publisher, bundle, cases, policy, _ = context
    job = RuleUpdateCoordinator(sessions)
    plan = await job.run(bundle, cases, policy, sync_sources=False)
    assert plan.status == "PLANNED"
    assert plan.regression["passed"]
    pending = await job.run(bundle, cases, policy, sync_sources=False, publish=True, publication_policy=trust(plan))
    assert pending.reason_code == "CANDIDATE_NOT_APPROVED"
    await publisher.approve(plan.candidate_version_id, {"regression_cases": regressions()})
    pending = await job.run(bundle, cases, policy, sync_sources=False, publish=True)
    assert pending.reason_code == "NO_TRUSTED_APPROVAL"
    result = await job.run(bundle, cases, policy, sync_sources=False, publish=True, publication_policy=trust(plan))
    assert result.status == "PUBLISHED"
    rerun = await job.run(bundle, cases, policy, sync_sources=False, publish=True, publication_policy=trust(plan))
    assert rerun.status == "UNCHANGED"
    async with sessions() as session:
        state = await session.get(RuleEngineState, 1)
        assert state.revision == 2 and state.active_version_id == plan.candidate_version_id
        assert await session.scalar(select(func.count()).select_from(RulePublication)) == 2
        run = await session.get(RuleSyncRun, result.run_id)
        assert run.status == "SUCCEEDED" and run.summary["status"] == "PUBLISHED"
        assert "A123456" not in json.dumps(run.summary)
        assert "CHAN DEMO" not in json.dumps(run.summary)


async def test_metadata_changes_do_not_create_rule_versions(context):
    sessions, _, bundle, cases, policy, _ = context
    async with sessions() as session:
        base = await session.get(RuleVersion, bundle.base_version_id)
        changed = json.loads(json.dumps(base.rules))
    changed["jurisdictions"]["HK"][0]["source_section"] = "New title"
    result = await RuleUpdateCoordinator(sessions).run(
        bundle.model_copy(update={"rules": changed}), cases, policy, sync_sources=False, publish=True
    )
    assert result.status == "METADATA_ONLY"
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(RuleVersion)) == 1
        assert (await session.get(RuleEngineState, 1)).revision == 1


async def test_stale_bundle_and_risky_change_never_activate(context):
    sessions, _, bundle, cases, policy, _ = context
    job = RuleUpdateCoordinator(sessions)
    stale = await job.run(bundle.model_copy(update={"base_version_id": "0" * 64}), cases, policy, sync_sources=False)
    assert stale.reason_code == "STALE_BASE_VERSION"
    restrictive = json.loads(json.dumps(bundle.rules))
    restrictive["jurisdictions"]["HK"][0]["regex"] = "[B-Z][0-9]{6}[0-9A]"
    risky = bundle.model_copy(update={"rules": restrictive, "regression_cases": regressions("B1234563")})
    result = await job.run(risky, cases, policy, sync_sources=False, publish=True)
    assert result.reason_code == "IMPACT_REQUIRES_MANUAL_PUBLICATION"
    assert "PASS_BECAME_BLOCKED" in result.impact.risks
    async with sessions() as session:
        assert (await session.get(RuleEngineState, 1)).revision == 1


async def test_evidence_and_trust_are_independent_gates(context):
    sessions, publisher, bundle, cases, policy, _ = context
    job = RuleUpdateCoordinator(sessions)
    plan = await job.run(bundle, cases, policy, sync_sources=False)
    await publisher.approve(plan.candidate_version_id, {"regression_cases": regressions()})
    missing = await job.run(
        bundle.model_copy(update={"documents": []}),
        cases,
        policy,
        sync_sources=False,
        publish=True,
        publication_policy=trust(plan),
    )
    assert missing.reason_code == "MISSING_CURRENT_SOURCE_EVIDENCE"
    bad_trust = trust(plan)
    bad_trust.approvals[0].evidence_hash = "0" * 64
    mismatch = await job.run(bundle, cases, policy, sync_sources=False, publish=True, publication_policy=bad_trust)
    assert mismatch.reason_code == "NO_TRUSTED_APPROVAL"
    async with sessions() as session:
        assert (await session.get(RuleEngineState, 1)).revision == 1


async def test_source_failure_waiting_and_cas_conflict_are_recorded(context):
    sessions, publisher, bundle, cases, policy, source_id = context
    importer = AsyncMock()
    importer.sync.return_value = {
        "run_id": "mock",
        "status": "PARTIAL",
        "sources": [
            {"source_id": source_id, "status": "FAILED", "error": "PRIVATE SOURCE ERROR"},
        ],
    }
    job = RuleUpdateCoordinator(sessions, importer)
    result = await job.run(bundle, cases, policy)
    assert result.reason_code == "SOURCE_SYNC_FAILED"
    assert "PRIVATE" not in result.model_dump_json()
    waiting = await job.run(None, cases, policy, sync_sources=False)
    assert waiting.status == "WAITING_FOR_BUNDLE"
    plan = await job.run(bundle, cases, policy, sync_sources=False)
    await publisher.approve(plan.candidate_version_id, {"regression_cases": regressions()})
    with patch.object(job.publisher, "activate", AsyncMock(side_effect=ConflictException("private details"))):
        conflict = await job.run(
            bundle, cases, policy, sync_sources=False, publish=True, publication_policy=trust(plan)
        )
    assert conflict.status == "CONFLICT" and "private" not in conflict.model_dump_json()
    async with sessions() as session:
        assert (await session.get(RuleEngineState, 1)).revision == 1
        assert (await session.get(RuleSyncRun, conflict.run_id)).status == "FAILED"


async def test_upstream_trust_flags_are_not_accepted(context):
    _, _, bundle, _, _, _ = context
    with pytest.raises(ValueError):
        RuleBundle.model_validate(bundle.model_dump() | {"trusted": True})
    assert canonical_hash(bundle.rules) != bundle.base_version_id


async def test_regression_failure_and_missing_baseline_do_not_publish(context):
    sessions, _, bundle, cases, policy, _ = context
    job = RuleUpdateCoordinator(sessions)
    bad = bundle.model_copy(update={"regression_cases": regressions("!")})
    failed = await job.run(bad, cases, policy, sync_sources=False, publish=True)
    assert failed.reason_code == "REGRESSION_FAILED"
    async with sessions.begin() as session:
        state = await session.get(RuleEngineState, 1)
        state.active_version_id = None
        state.activated_at = None
    empty = await job.run(bundle, cases, policy, sync_sources=False, publish=True)
    assert empty.status == "NO_ACTIVE_RULES"
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(RulePublication)) == 1


async def test_missing_or_stale_document_evidence_cannot_publish(context):
    from datetime import timedelta

    from backend.models import RuleDocument

    sessions, publisher, bundle, cases, policy, source_id = context
    job = RuleUpdateCoordinator(sessions)
    plan = await job.run(bundle, cases, policy, sync_sources=False)
    await publisher.approve(plan.candidate_version_id, {"regression_cases": regressions()})
    async with sessions.begin() as session:
        repo = RuleRepository(session)
        run = await repo.start_sync()
        newer = await repo.store_document(source_id, run.id, b"%PDF-1.7 newer synthetic evidence", "application/pdf")
        newer.fetched_at = datetime.now(UTC) + timedelta(seconds=1)
        await repo.finish_sync(run.id, "SUCCEEDED", {})
    result = await job.run(bundle, cases, policy, sync_sources=False, publish=True, publication_policy=trust(plan))
    assert result.reason_code == "MISSING_CURRENT_SOURCE_EVIDENCE"
    async with sessions() as session:
        assert (await session.get(RuleEngineState, 1)).revision == 1
        original = await session.get(RuleDocument, bundle.documents[0].document_id)
        assert original.content_hash == bundle.documents[0].content_hash


@pytest.mark.parametrize("same_rules", [True, False])
async def test_changed_source_is_not_hidden_by_an_old_unchanged_bundle(context, same_rules):
    sessions, _, bundle, cases, policy, source_id = context
    async with sessions() as session:
        base = await session.get(RuleVersion, bundle.base_version_id)
        old_bundle = bundle.model_copy(update={"rules": base.rules}) if same_rules else bundle
    importer = AsyncMock()
    importer.sync.return_value = {
        "run_id": "source-run",
        "status": "SUCCEEDED",
        "sources": [
            {"source_id": source_id, "document_id": "new-document", "status": "IMPORTED"},
        ],
    }
    result = await RuleUpdateCoordinator(sessions, importer).run(old_bundle, cases, policy)
    assert result.status == "WAITING_FOR_BUNDLE"
    assert result.reason_code == "NEW_SOURCE_REQUIRES_UPSTREAM_REVIEW"


async def test_source_import_through_hot_reload_end_to_end(context):
    import httpx

    from backend.engine.rule_loader import RuleLoader
    from backend.engine.tin_validator import TINValidatorEngine
    from backend.services.rule_import import RuleSourceImporter

    sessions, publisher, bundle, cases, policy, _ = context
    loader = RuleLoader(sessions)
    original = await loader.refresh()
    plan = await RuleUpdateCoordinator(sessions).run(bundle, cases, policy, sync_sources=False)
    await publisher.approve(plan.candidate_version_id, {"regression_cases": regressions()})
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                content=b"%PDF-1.7 synthetic test evidence",
                headers={"Content-Type": "application/pdf", "ETag": '"v1"'},
            )
        )
    ) as client:
        job = RuleUpdateCoordinator(sessions, RuleSourceImporter(sessions, client))
        published = await job.run(bundle, cases, policy, publication_policy=trust(plan), publish=True)
    assert published.status == "PUBLISHED"
    assert published.source_sync["unchanged"] == 1
    current = await loader.refresh()
    assert current.version_id == plan.candidate_version_id and current.revision == original.revision + 1
    assert original.version_id == bundle.base_version_id
    validator = TINValidatorEngine()
    assert validator.evaluate("AB1234563", "HK", original, "INDIVIDUAL", "HKID")[1].status == "FAILED"
    assert validator.evaluate("AB1234563", "HK", current, "INDIVIDUAL", "HKID")[1].status == "PASSED"


async def test_cli_run_writes_atomic_plan_and_has_no_hidden_approval(context, tmp_path, monkeypatch, capsys):
    import argparse
    from types import SimpleNamespace

    import backend.infrastructure.database as database
    from backend.cli.rule_updates import run_command

    sessions, _, bundle, cases, policy, _ = context
    path = tmp_path / "bundle.json"
    path.write_text(bundle.model_dump_json(), encoding="utf-8")
    samples = tmp_path / "cases.json"
    samples.write_text(json.dumps(cases), encoding="utf-8")
    output = tmp_path / "output" / "plan.json"
    monkeypatch.setattr(database, "async_session_factory", sessions)
    dispose = AsyncMock()
    monkeypatch.setattr(database, "engine", SimpleNamespace(dispose=dispose))
    args = argparse.Namespace(
        bundle=path,
        policy=None,
        today=policy.today.isoformat(),
        timezone="Asia/Shanghai",
        earliest_date=None,
        cases=samples,
        publish=False,
        skip_source_sync=True,
        scheduled=True,
        output=output,
    )
    assert await run_command(args) == 0
    data = json.loads(capsys.readouterr().out)
    assert data == json.loads(output.read_text(encoding="utf-8"))
    assert data["status"] == "PLANNED"
    dispose.assert_awaited_once()
    async with sessions() as session:
        assert (await session.get(RuleEngineState, 1)).revision == 1
        assert (await session.get(RuleVersion, data["candidate_version_id"])).status == "CANDIDATE"
