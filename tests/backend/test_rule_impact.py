"""Rule upgrade effects and privacy, independent of model and database availability."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from backend.engine.contracts import ValidationPolicy
from backend.engine.impact import analyze_impact
from backend.engine.reproducibility import canonical_hash
from backend.engine.rule_loader import RuleLoader, compile_snapshot
from backend.engine.validation import ValidationEngine
from backend.infrastructure.database import async_session_factory


def snapshot(rules, revision=0):
    return compile_snapshot(canonical_hash(rules), revision, rules)


def evaluate(before, after, cases=None):
    engine = ValidationEngine(RuleLoader(async_session_factory))
    return analyze_impact(
        engine,
        snapshot(before, 2),
        snapshot(after, 3),
        cases or json.loads(Path("assets/mock-data/cases.json").read_text(encoding="utf-8")),
        ValidationPolicy.model_validate({"today": "2026-11-04"}),
    )


def test_demo_upgrade_reports_exact_effects_without_private_form_values():
    base = json.loads(Path("rules/rules_v1_base.json").read_text(encoding="utf-8"))
    patch = json.loads(Path("rules/rules_v2_patch.json").read_text(encoding="utf-8"))
    report = evaluate(base, patch)
    assert report.sample_count == 5
    case_e = next(row for row in report.cases if row["case_id"] == "E")
    assert case_e["before"]["verdict"] == "MANUAL_TRIAGE"
    assert case_e["after"]["verdict"] == "NEED_USER_FIX"
    assert report.rule_changes
    assert report.report_hash == canonical_hash(report.model_dump(mode="json", exclude={"report_hash"}))
    serialized = report.model_dump_json()
    assert "11010519491231002X" not in serialized
    assert "DEMO PERSON" not in serialized
    assert "1949-12-31" not in serialized
    assert evaluate(base, patch).report_hash == report.report_hash


def test_removal_downgrade_relaxation_and_metadata_are_distinguished():
    rules = json.loads(Path("rules/rules_global_v4.json").read_text(encoding="utf-8"))
    removed = json.loads(json.dumps(rules))
    del removed["jurisdictions"]["HK"]
    assert "SELECTOR_REMOVED" in evaluate(rules, removed).risks
    downgraded = json.loads(json.dumps(rules))
    cn = downgraded["jurisdictions"]["CN"][0]
    cn.update(algorithm="REGEX_ONLY", verification_level="FORMAT_ONLY")
    report = evaluate(rules, downgraded)
    assert "VERIFICATION_DOWNGRADED" in report.risks
    assert "VERDICT_RELAXED" in report.risks
    metadata = json.loads(json.dumps(rules))
    metadata["jurisdictions"]["CN"][0]["source_section"] = "Updated heading"
    report = evaluate(rules, metadata)
    assert report.changed_case_count == 0
    assert all(not change.execution_changed for change in report.rule_changes)
    assert report.rule_changes[0].changed_fields == ["source_section"]


def test_impact_supports_multi_residence_and_rejects_duplicate_cases():
    rules = json.loads(Path("rules/rules_global_v4.json").read_text(encoding="utf-8"))
    request = json.loads(Path("assets/crs-templates/crs-multi-residence-request.json").read_text(encoding="utf-8"))
    cases = [{"case_id": "MULTI", "form_data": request["form_data"]}]
    report = evaluate(rules, rules, cases)
    assert len(report.cases[0]["after"]["residences"]) == 2
    assert not report.risks and not report.rule_changes
    with pytest.raises(ValueError):
        evaluate(rules, rules, cases * 2)
    report2 = evaluate(rules, rules, [cases[0] | {"form_data": request["form_data"] | {"holder_name": "Changed"}}])
    assert report.suite_hash != report2.suite_hash


def test_offline_cli_runs_without_a_database_or_model():
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "backend.cli.rule_updates",
            "impact",
            "--base",
            "rules/rules_v1_base.json",
            "--candidate",
            "rules/rules_v2_patch.json",
            "--today",
            "2026-11-04",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(result.stdout)["sample_count"] == 5


def test_removed_blocker_is_detected_even_when_other_blockers_mask_verdict_change():
    base = json.loads(Path("rules/rules_global_v4.json").read_text(encoding="utf-8"))
    relaxed = json.loads(json.dumps(base))
    relaxed["jurisdictions"]["CN"][0].update(algorithm="REGEX_ONLY", verification_level="FORMAT_ONLY")
    case = json.loads(Path("assets/mock-data/cases.json").read_text(encoding="utf-8"))[1]
    case["form_data"]["has_signature"] = False
    report = evaluate(base, relaxed, [case])
    assert report.cases[0]["before"]["verdict"] == report.cases[0]["after"]["verdict"] == "NEED_USER_FIX"
    assert "BLOCKER_REMOVED" in report.risks
