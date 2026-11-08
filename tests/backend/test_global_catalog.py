"""Official catalog format boundaries; sample strings are not real tax IDs."""

import json
from pathlib import Path

import pytest

from backend.cli.demo_cases import snapshot
from backend.engine.tin_validator import TINValidatorEngine

CATALOG = json.loads(Path("rules/rules_global_v3.json").read_text())


@pytest.mark.parametrize(
    ("code", "holder", "kind", "value"),
    [
        ("US", "INDIVIDUAL", "US_ITIN", "912345678"),
        ("CA", "ENTITY", "CA_TRUST", "T12345678"),
        ("AU", "ENTITY", "AU_ABN", "12345678901"),
        ("DE", "INDIVIDUAL", "DE_IDNR", "12345678901"),
        ("FR", "INDIVIDUAL", "FR_SPI", "0123456789012"),
        ("JP", "ENTITY", "JP_CORPORATE", "1234567890123"),
        ("IN", "INDIVIDUAL", "IN_PAN", "ABCPD1234A"),
        ("NZ", "ENTITY", "NZ_IRD", "12-345-678"),
        ("CH", "ENTITY", "CH_UID", "CHE-123.456.789"),
        ("NL", "INDIVIDUAL", "NL_TIN", "123456789"),
        ("KR", "ENTITY", "KR_BRN", "123-45-67890"),
        ("ES", "INDIVIDUAL", "ES_NIE", "X1234567A"),
        ("IE", "ENTITY", "IE_CHY", "CHY 12345"),
        ("ZA", "ENTITY", "ZA_INCOME_TAX", "0123456789"),
        ("SE", "INDIVIDUAL", "SE_PERSONNUMMER", "123456+7890"),
        ("NO", "ENTITY", "NO_ORGNR", "812345678MVA"),
        ("DK", "ENTITY", "DK_CVR", "12345678"),
        ("PL", "INDIVIDUAL", "PL_PESEL", "12345678901"),
        ("GB", "INDIVIDUAL", "GB_NINO", "AB 12 34 56 C"),
    ],
)
def test_supported_structural_shapes(code, holder, kind, value):
    engine = TINValidatorEngine()
    rules = snapshot(CATALOG, 1)
    assert engine.validate(value, code, rules, holder, kind) == []
    trace = engine.trace(value, code, rules, holder, kind)
    assert trace.status == "PASSED"
    assert trace.verification_level == "FORMAT_ONLY"
    assert trace.source_url.startswith("https://")
    assert trace.rule_id
    assert engine.validate("!", code, rules, holder, kind)[0].code == "INVALID_TIN"


def test_uncovered_country_is_not_automatic_pass():
    rules = snapshot(CATALOG, 1)
    validator = TINValidatorEngine()
    assert validator.validate("12345678", "ZZ", rules, "ENTITY", "UNKNOWN")[0].code == "UNSUPPORTED_JURISDICTION"
    assert validator.trace("12345678", "ZZ", rules, "ENTITY", "UNKNOWN").status == "NOT_COVERED"
    assert validator.validate("12345678", "DE", rules, "ENTITY", "DE_UNKNOWN")[0].code == "UNSUPPORTED_TIN_TYPE"


def test_rule_provenance_and_hmrc_exclusions():
    assert len(CATALOG["jurisdictions"]) == 22
    for variants in CATALOG["jurisdictions"].values():
        for rule in variants:
            assert rule["reviewed_on"] == "2026-11-02"
            assert rule["source_section"]
            assert rule["limitations"]
    rules = snapshot(CATALOG, 1)
    validator = TINValidatorEngine()
    for value in ["QQ123456A", "BG123456A", "AB123456E", "AO123456A"]:
        assert validator.validate(value, "GB", rules, "INDIVIDUAL", "GB_NINO")
