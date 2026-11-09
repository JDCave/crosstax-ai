"""Execute real regression cases before approval, rather than trusting report claims."""

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, TypeAdapter

from backend.engine.reproducibility import canonical_hash
from backend.engine.rule_loader import RuleSnapshot
from backend.engine.tin_validator import TINValidatorEngine


class RegressionCase(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    case_id: str
    jurisdiction_code: str
    holder_type: str = ""
    tin_type: str = ""
    tin: str | None
    valid: bool


def run_regressions(snapshot: RuleSnapshot, supplied: object = None) -> dict[str, object]:
    raw = (
        supplied
        if supplied is not None
        else json.loads((Path(__file__).parent / "corpus/rule_regressions.json").read_text(encoding="utf-8"))
    )
    if not isinstance(raw, list) or len(raw) > 5000:
        raise ValueError("Regression suite must have at most 5000 cases")
    cases = TypeAdapter(list[RegressionCase]).validate_python(raw)
    if len({case.case_id for case in cases}) != len(cases):
        raise ValueError("Regression case IDs must be unique")
    selectors = set(snapshot.variants) or {(code, "", "") for code in snapshot.rules}
    seen: dict[tuple[str, str, str], set[bool]] = {}
    failures: list[str] = []
    count = 0
    validator = TINValidatorEngine()
    for case in cases:
        key = (case.jurisdiction_code, case.holder_type, case.tin_type)
        if key not in selectors:
            continue
        seen.setdefault(key, set()).add(case.valid)
        issues, trace = validator.evaluate(
            case.tin, case.jurisdiction_code, snapshot, case.holder_type, case.tin_type, strict_coverage=True
        )
        actual = not issues and trace.status == "PASSED"
        if actual != case.valid:
            failures.append(case.case_id)
        count += 1
    missing = ["/".join(key) for key in selectors if seen.get(key) != {True, False}]
    if failures or missing:
        raise ValueError(f"Regression gate rejected: failed={failures}; missing_positive_or_negative={missing}")
    return {
        "passed": True,
        "executed_cases": count,
        "covered_selectors": len(selectors),
        "suite_hash": canonical_hash([case.model_dump() for case in cases]),
    }
