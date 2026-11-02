"""Deep-rule catalog integration and official structural exceptions."""

import json
from pathlib import Path

import pytest

from backend.cli.demo_cases import snapshot
from backend.engine.tin_validator import TINValidatorEngine

RULES = snapshot(json.loads(Path("rules/rules_global_v4.json").read_text()), 1)


@pytest.mark.parametrize(
    ("code", "holder", "kind", "valid", "invalid"),
    [
        ("AU", "ENTITY", "AU_ABN", "51824753556", "51824753557"),
        ("JP", "ENTITY", "JP_CORPORATE", "8700110005901", "9700110005901"),
        ("PL", "INDIVIDUAL", "PL_PESEL", "02070803628", "02070803629"),
        ("PL", "ENTITY", "PL_NIP", "2234567895", "2234567896"),
        ("NL", "INDIVIDUAL", "NL_TIN", "123456782", "123456783"),
        ("NO", "ENTITY", "NO_ORGNR", "974760673MVA", "974760674MVA"),
    ],
)
def test_catalog_checksum_dispatch(code, holder, kind, valid, invalid):
    validator = TINValidatorEngine()
    assert validator.validate(valid, code, RULES, holder, kind) == []
    assert validator.validate(invalid, code, RULES, holder, kind)[0].code == "INVALID_TIN"
    trace = validator.trace(valid, code, RULES, holder, kind)
    assert trace.verification_level == "CHECKSUM"
    assert trace.algorithm_source_url.startswith("https://")


@pytest.mark.parametrize("value", ["000123456", "666123456", "900123456", "123003456", "123450000"])
def test_ssa_invalid_groups(value):
    assert TINValidatorEngine().validate(value, "US", RULES, "INDIVIDUAL", "US_SSN")


@pytest.mark.parametrize("group", ["50", "65", "70", "88", "90", "92", "94", "99"])
def test_irs_itin_allowed_ranges(group):
    assert TINValidatorEngine().validate("912" + group + "1234", "US", RULES, "INDIVIDUAL", "US_ITIN") == []


@pytest.mark.parametrize("group", ["49", "66", "69", "89", "93"])
def test_irs_itin_excluded_ranges(group):
    assert TINValidatorEngine().validate("912" + group + "1234", "US", RULES, "INDIVIDUAL", "US_ITIN")


def test_german_business_id_keeps_personal_id_separate():
    validator = TINValidatorEngine()
    assert validator.validate("DE123456789-00001", "DE", RULES, "ENTITY", "DE_WIDNR_ACTIVITY") == []
    assert validator.validate("DE123456789", "DE", RULES, "ENTITY", "DE_WIDNR") == []
    assert validator.validate("DE123456789-0001", "DE", RULES, "ENTITY", "DE_WIDNR_ACTIVITY")
    assert validator.validate("DE123456789", "DE", RULES, "INDIVIDUAL", "DE_IDNR")
