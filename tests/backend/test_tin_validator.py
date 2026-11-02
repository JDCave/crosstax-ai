"""Checksum vectors, malformed inputs, rule dispatch and snapshot isolation."""

import hashlib
import json

import pytest

from backend.engine.rule_loader import compile_snapshot
from backend.engine.tin_validator import TINValidatorEngine, hkid_weight, mod11_2, nric_weight


@pytest.mark.parametrize(
    ("operator", "valid", "invalid"),
    [
        (mod11_2, "11010519491231002X", "110105194912310021"),
        (hkid_weight, "A1234563", "A1234564"),
        (hkid_weight, "AA1234566", "AA1234567"),
        (nric_weight, "S0000001I", "S0000001J"),
        (nric_weight, "T0000001E", "T0000001J"),
    ],
)
def test_checksum_vectors(operator, valid, invalid):
    assert operator(valid)
    assert not operator(invalid)
    assert not operator("")
    assert not operator("１２３４５６７８９")  # noqa: RUF001 -- intentional non-ASCII digits


def snapshot(rules):
    digest = hashlib.sha256(json.dumps(rules, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return compile_snapshot(digest, 1, rules)


def test_dispatch_normalization_and_fallback():
    rules = snapshot({"HK": {"regex": "[A-Z]{1,2}[0-9]{6}[0-9A]", "algorithm": "HKID_WEIGHT"}})
    engine = TINValidatorEngine()
    assert engine.validate(" a-123456(3) ", "hk", rules) == []
    issues = engine.validate("A1234564", "HK", rules)
    assert issues[0].model_dump() == {
        "code": "INVALID_TIN",
        "severity": "BLOCKER",
        "field": "tin",
        "message": "TIN 校验位或标识类型不符合当前规则。请核对后重新提交",
        "confidence": 1.0,
    }
    for value in (None, "", "123", "1" * 31, "1" * 257):
        assert engine.validate(value, "ZZ", rules)
    assert engine.validate("1234", "ZZ", rules) == []
    assert engine.validate("1" * 30, "ZZ", rules) == []


def test_regex_only_and_old_version_remain_independent():
    engine = TINValidatorEngine()
    old = snapshot({"HK": {"regex": "[0-9]{8}", "algorithm": "REGEX_ONLY"}})
    new = snapshot({"HK": {"regex": "[0-9]{9}", "algorithm": "REGEX_ONLY"}})
    assert engine.validate("12345678", "HK", old) == []
    assert engine.validate("12345678", "HK", new)
    assert engine.validate("12345678", "HK", old) == []
