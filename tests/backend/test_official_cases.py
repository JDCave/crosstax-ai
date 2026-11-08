"""Repository source-backed rules, case fixtures and typed rule isolation."""

from datetime import date

from backend.cli.demo_cases import read_rules, run_cases, snapshot
from backend.engine.contracts import CRSFormData, ValidationPolicy
from backend.engine.rule_loader import RuleLoader
from backend.engine.validation import ValidationEngine
from backend.infrastructure.database import async_session_factory


def test_case_a_to_e():
    results = run_cases()
    assert [row["case_id"] for row in results] == list("ABCDE")
    assert [row["verdict"] for row in results] == [
        "AUTO_PASS",
        "NEED_USER_FIX",
        "NEED_USER_FIX",
        "MANUAL_TRIAGE",
        "NEED_USER_FIX",
    ]


def test_type_selection_and_enterprise_rules():
    rules = snapshot(read_rules("rules_v2_patch.json"), 1)
    engine = ValidationEngine(RuleLoader(async_session_factory))
    base = dict(
        holder_name="DEMO",
        holder_dob="2000-01-01",
        residence_address="DEMO",
        jurisdiction_code="HK",
        holder_type="ENTITY",
        tin_type="HK_BR",
        tin="12345678",
        has_no_tin=False,
        has_signature=True,
        signing_date="2026-11-01",
    )
    policy = ValidationPolicy(today=date(2026, 11, 2))
    result = engine.validate_snapshot(CRSFormData.model_validate(base), policy, rules)
    assert result.verdict == "AUTO_PASS"
    mismatched = base | {"holder_type": "INDIVIDUAL"}
    result = engine.validate_snapshot(CRSFormData.model_validate(mismatched), policy, rules)
    assert result.verdict == "MANUAL_TRIAGE"
    assert result.form_issues[0].code == "UNSUPPORTED_TIN_TYPE"
    for kind, value in [("SG_UEN_ROB", "12345678A"), ("SG_UEN_ROC", "202600001A"), ("SG_UEN_OTHER", "T26LL0001A")]:
        form = CRSFormData.model_validate(base | {"jurisdiction_code": "SG", "tin_type": kind, "tin": value})
        assert engine.validate_snapshot(form, policy, rules).verdict == "AUTO_PASS"
