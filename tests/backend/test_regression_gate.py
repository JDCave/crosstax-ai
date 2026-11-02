"""Catalog-wide coverage and false approval-report rejection."""

import json
from pathlib import Path

import pytest

from backend.cli.demo_cases import snapshot
from backend.engine.regression import run_regressions


def test_all_66_selectors_have_positive_negative_and_boundaries():
    rules = json.loads(Path("rules/rules_global_v4.json").read_text())
    result = run_regressions(snapshot(rules, 1))
    assert result == {"passed": True, "executed_cases": 264, "covered_selectors": 66}


def test_missing_cases_and_changed_rule_fail_closed():
    rules = json.loads(Path("rules/rules_global_v4.json").read_text())
    with pytest.raises(ValueError, match="missing"):
        run_regressions(snapshot(rules, 1), [])
    rules["jurisdictions"]["HK"][1]["regex"] = "[0-9]{9}"
    with pytest.raises(ValueError, match="failed"):
        run_regressions(snapshot(rules, 1))
