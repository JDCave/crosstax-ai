"""Run the repository Case A-E suite and optionally install validated rules."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path

from backend.engine.contracts import AuditIssue, CRSFormData, ValidationPolicy
from backend.engine.publication import RulePublisher
from backend.engine.rule_loader import RuleLoader, RuleSnapshot, compile_snapshot
from backend.engine.validation import ValidationEngine
from backend.infrastructure.database import async_session_factory, engine
from backend.models import RuleEngineState, RuleVersion

ROOT = Path(__file__).resolve().parents[2]


def read_rules(name: str) -> dict[str, object]:
    from backend.cli.rule_engine import read_object

    return read_object(ROOT / "rules" / name)


def snapshot(rules: dict[str, object], revision: int) -> RuleSnapshot:
    content = json.dumps(rules, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return compile_snapshot(hashlib.sha256(content.encode()).hexdigest(), revision, rules)


def run_cases() -> list[dict[str, str]]:
    base = snapshot(read_rules("rules_v1_base.json"), 1)
    latest = snapshot(read_rules("rules_v2_patch.json"), 2)
    validator = ValidationEngine(RuleLoader(async_session_factory))
    policy = ValidationPolicy.model_validate({"today": "2026-11-02"})
    cases = json.loads((ROOT / "assets/mock-data/cases.json").read_text())
    results = []
    for case in cases:
        form = CRSFormData.model_validate(case["form_data"])
        issues = [AuditIssue.model_validate(item) for item in case["indicia_issues"]]
        if case["case_id"] == "E":
            before = validator.validate_snapshot(form, policy, base, issues)
            if before.verdict != case["expected_before_reload"]:
                raise ValueError("Case E before-reload result differs")
        result = validator.validate_snapshot(form, policy, latest, issues)
        if result.verdict != case["expected_verdict"]:
            raise ValueError(f"Case {case['case_id']} failed: {result.verdict}")
        results.append(
            {"case_id": case["case_id"], "verdict": result.verdict, "rule_version_id": result.rule_version_id}
        )
    return results


async def install() -> str:
    publisher = RulePublisher(async_session_factory)
    latest_id = ""
    for name in ("rules_v1_base.json", "rules_v2_patch.json"):
        latest_id = await publisher.register(read_rules(name), [])
        async with async_session_factory() as session:
            version = await session.get(RuleVersion, latest_id)
            status = version.status if version else None
        if status == "CANDIDATE":
            await publisher.approve(
                latest_id,
                {
                    "cases_passed": ["A", "B", "C", "D", "E"],
                    "source": "repository reviewed baseline",
                    "synthetic_cases": True,
                },
            )
        elif status != "APPROVED":
            raise ValueError("Existing baseline was rejected; cannot activate")
    async with async_session_factory() as session:
        state = await session.get(RuleEngineState, 1)
        if state is None:
            raise ValueError("Missing rule_engine_state singleton; apply database setup first")
        revision = state.revision
        already_active = state.active_version_id == latest_id
    if not already_active:
        await publisher.activate(latest_id, revision)
    return latest_id


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install", action="store_true", help="Store approved baseline versions and activate latest")
    args = parser.parse_args()
    try:
        results = run_cases()
        print(json.dumps(results, ensure_ascii=False, indent=2))
        if args.install:
            print(json.dumps({"active_version_id": await install()}))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
