"""Single-pass tracing must distinguish configured from executed checks."""

from unittest.mock import patch

from backend.engine.contracts import CRSFormData
from backend.engine.tin_validator import TINValidatorEngine
from tests.backend.test_audit_completeness import BASE, ENGINE, POLICY, RULES


def test_one_tin_evaluation_per_audit():
    with patch.object(ENGINE.tin_validator, "evaluate", wraps=ENGINE.tin_validator.evaluate) as evaluate:
        result = ENGINE.validate_snapshot(CRSFormData.model_validate(BASE), POLICY, RULES)
        assert evaluate.call_count == 1
    assert result.tin_check.checks_performed == ("rule_selection", "normalization", "format", "checksum")
    assert "issuance" in result.tin_check.checks_not_performed


def test_format_failure_does_not_claim_checksum_executed():
    issues, trace = TINValidatorEngine().evaluate("ABC", "CN", RULES, "INDIVIDUAL", "CN_ID")
    assert issues
    assert trace.reason_code == "FORMAT_MISMATCH"
    assert trace.verification_level == "FORMAT_ONLY"
    assert "checksum" not in trace.checks_performed
    assert "checksum" in trace.checks_not_performed


def test_uncovered_and_exempt_are_explained():
    issues, trace = TINValidatorEngine().evaluate("1234", "ZZ", RULES, "ENTITY", "UNKNOWN")
    assert issues and trace.status == "NOT_COVERED"
    assert trace.verification_level == "NONE"
    result = ENGINE.validate_snapshot(
        CRSFormData.model_validate(BASE | {"has_no_tin": True, "tin": None, "tin_reason_code": "A"}), POLICY, RULES
    )
    assert "exemption_applicability" in result.tin_check.checks_not_performed
    assert result.tin_check.reason_code == "EXEMPTION_REVIEW_REQUIRED"
