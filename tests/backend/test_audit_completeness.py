"""Conservative exemption handling and contradictory input regression tests."""

import json
from datetime import date
from pathlib import Path

import pytest

from backend.cli.demo_cases import snapshot
from backend.engine.contracts import CRSFormData, ValidationPolicy
from backend.engine.rule_loader import RuleLoader
from backend.engine.validation import ValidationEngine
from backend.infrastructure.database import async_session_factory

BASE = json.loads(Path("assets/mock-data/cases.json").read_text())[0]["form_data"]
RULES = snapshot(json.loads(Path("rules/rules_global_v4.json").read_text()), 1)
POLICY = ValidationPolicy(today=date(2026, 11, 3))
ENGINE = ValidationEngine(RuleLoader(async_session_factory))


@pytest.mark.parametrize("reason", ["A", "B", "C"])
def test_exemption_never_claims_applicability(reason):
    form = CRSFormData.model_validate(
        BASE
        | {"has_no_tin": True, "tin": None, "tin_reason_code": reason, "tin_reason_explanation": "Example explanation"}
    )
    result = ENGINE.validate_snapshot(form, POLICY, RULES)
    assert result.verdict == "MANUAL_TRIAGE"
    assert any(issue.code == "EXEMPTION_REVIEW_REQUIRED" for issue in result.form_issues)


@pytest.mark.parametrize(
    "changes",
    [
        {"has_no_tin": True, "tin_reason_code": "A"},
        {"has_no_tin": False, "tin_reason_code": "A"},
        {"holder_name": "   "},
        {"residence_address": "\t"},
        {"holder_dob": "2026-02-30"},
    ],
)
def test_incomplete_or_contradictory_input_blocks(changes):
    result = ENGINE.validate_snapshot(CRSFormData.model_validate(BASE | changes), POLICY, RULES)
    assert result.verdict == "NEED_USER_FIX"


def test_unknown_exemption_and_legacy_unknown_country_need_review():
    form = CRSFormData.model_validate(
        BASE | {"jurisdiction_code": "ZZ", "tin": None, "has_no_tin": True, "tin_reason_code": "A"}
    )
    assert ENGINE.validate_snapshot(form, POLICY, RULES).verdict == "MANUAL_TRIAGE"
    legacy = snapshot({"CN": {"regex": "[0-9]+", "algorithm": "REGEX_ONLY"}}, 1)
    form = CRSFormData.model_validate(BASE | {"jurisdiction_code": "ZZ", "tin": "12345678"})
    assert ENGINE.validate_snapshot(form, POLICY, legacy).verdict == "MANUAL_TRIAGE"
    compatible = ValidationPolicy(today=date(2026, 11, 3), strict_coverage=False)
    assert ENGINE.validate_snapshot(form, compatible, legacy).verdict == "AUTO_PASS"
