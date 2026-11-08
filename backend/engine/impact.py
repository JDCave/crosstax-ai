"""Deterministic, PII-minimized comparison of two rule snapshots on explicit samples."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from backend.engine.contracts import AuditIssue, CRSFormData, ValidationPolicy
from backend.engine.document_contracts import MultiResidenceForm
from backend.engine.document_validation import DocumentResult, validate_document
from backend.engine.reproducibility import canonical_hash, engine_build_id
from backend.engine.rule_loader import CompiledRule, RuleSnapshot
from backend.engine.structured_contracts import FormData
from backend.engine.structured_validation import load_form_policy, validate_structured
from backend.engine.validation import ValidationEngine


class ImpactCase(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    case_id: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,100}$")
    form_data: CRSFormData | MultiResidenceForm | FormData
    indicia_issues: list[AuditIssue] = Field(default_factory=list, max_length=100)
    # Explicitly support existing demo wrappers; these are not expected-result assertions.
    synthetic: bool | None = None
    merchant_id: str | None = None
    expected_before_reload: Literal["AUTO_PASS", "NEED_USER_FIX", "MANUAL_TRIAGE"] | None = None
    expected_verdict: Literal["AUTO_PASS", "NEED_USER_FIX", "MANUAL_TRIAGE"] | None = None


class RuleChange(BaseModel):
    selector: tuple[str, str, str]
    change: Literal["ADDED", "REMOVED", "MODIFIED"]
    execution_changed: bool
    changed_fields: list[str]


class ImpactReport(BaseModel):
    base_version_id: str
    candidate_version_id: str
    base_revision: int
    engine_build_id: str
    policy: ValidationPolicy
    suite_hash: str
    sample_count: int
    changed_case_count: int
    transitions: dict[str, int]
    rule_changes: list[RuleChange]
    cases: list[dict[str, Any]]
    risks: list[str]
    report_hash: str
    form_policy_id: str | None = None


def selectors(snapshot: RuleSnapshot) -> dict[tuple[str, str, str], CompiledRule]:
    return dict(snapshot.variants) or {(code, "", ""): rule for code, rule in snapshot.rules.items()}


def rule_properties(rule: CompiledRule) -> dict[str, object]:
    return {
        "regex": rule.pattern.pattern,
        "algorithm": rule.algorithm,
        "verification_level": rule.verification_level,
        "rule_id": rule.rule_id,
        "source_url": rule.source_url,
        "algorithm_source_url": rule.algorithm_source_url,
        "source_section": rule.source_section,
        "limitations": rule.limitations,
    }


def compare_rules(base: RuleSnapshot, candidate: RuleSnapshot) -> list[RuleChange]:
    before, after = selectors(base), selectors(candidate)
    changes = []
    for key in sorted(before.keys() | after.keys()):
        if key not in before or key not in after:
            changes.append(
                RuleChange(
                    selector=key,
                    change="ADDED" if key not in before else "REMOVED",
                    execution_changed=True,
                    changed_fields=[],
                )
            )
            continue
        old, new = rule_properties(before[key]), rule_properties(after[key])
        fields = [name for name in old if old[name] != new[name]]
        if fields:
            changes.append(
                RuleChange(
                    selector=key,
                    change="MODIFIED",
                    changed_fields=fields,
                    execution_changed=bool(set(fields) & {"regex", "algorithm", "verification_level"}),
                )
            )
    return changes


def summarize(result: DocumentResult) -> dict[str, object]:
    return {
        "verdict": result.verdict,
        "findings": [
            {"code": issue.code, "field": issue.field, "severity": issue.severity} for issue in result.form_issues
        ],
        "upstream_issue_count": len(result.indicia_issues),
        "residences": [
            {
                "index": residence.index,
                "jurisdiction_code": residence.jurisdiction_code,
                "status": residence.checks.status,
                "verification_level": residence.checks.verification_level,
                "reason_code": residence.checks.reason_code,
            }
            for residence in result.residence_results
        ],
    }


def analyze_impact(
    engine: ValidationEngine,
    base: RuleSnapshot,
    candidate: RuleSnapshot,
    raw_cases: object,
    policy: ValidationPolicy,
) -> ImpactReport:
    if not isinstance(raw_cases, list) or not 1 <= len(raw_cases) <= 500:
        raise ValueError("Impact suite must contain 1-500 cases")
    cases = sorted(TypeAdapter(list[ImpactCase]).validate_python(raw_cases), key=lambda case: case.case_id)
    if len({case.case_id for case in cases}) != len(cases):
        raise ValueError("Duplicate impact case ID")
    changes = compare_rules(base, candidate)
    old_rules, new_rules = selectors(base), selectors(candidate)
    levels = {"NONE": 0, "FORMAT_ONLY": 1, "CHECKSUM": 2}
    risks: set[str] = set()
    for change in changes:
        if change.change == "REMOVED":
            risks.add("SELECTOR_REMOVED")
        if change.change == "MODIFIED" and (
            levels[new_rules[change.selector].verification_level]
            < levels[old_rules[change.selector].verification_level]
        ):
            risks.add("VERIFICATION_DOWNGRADED")
    form_policy = load_form_policy() if any(isinstance(case.form_data, FormData) for case in cases) else None
    rows = []
    transitions: dict[str, int] = {}
    rank = {"AUTO_PASS": 0, "MANUAL_TRIAGE": 1, "NEED_USER_FIX": 2}
    for case in cases:
        if isinstance(case.form_data, FormData):
            before = validate_structured(case.form_data, policy, base, case.indicia_issues, form_policy)
            after = validate_structured(case.form_data, policy, candidate, case.indicia_issues, form_policy)
        else:
            before = validate_document(engine, case.form_data, policy, base, case.indicia_issues)
            after = validate_document(engine, case.form_data, policy, candidate, case.indicia_issues)
        old, new = summarize(before), summarize(after)
        changed = old != new
        transition = before.verdict + "->" + after.verdict
        transitions[transition] = transitions.get(transition, 0) + 1
        old_blockers = {(issue.code, issue.field) for issue in before.form_issues if issue.severity == "BLOCKER"}
        new_blockers = {(issue.code, issue.field) for issue in after.form_issues if issue.severity == "BLOCKER"}
        if old_blockers - new_blockers:
            risks.add("BLOCKER_REMOVED")
        if rank[after.verdict] < rank[before.verdict]:
            risks.add("VERDICT_RELAXED")
        if before.verdict == "AUTO_PASS" and after.verdict == "NEED_USER_FIX":
            risks.add("PASS_BECAME_BLOCKED")
        for previous, current in zip(before.residence_results, after.residence_results, strict=True):
            if levels[current.checks.verification_level] < levels[previous.checks.verification_level]:
                risks.add("SAMPLE_VERIFICATION_DOWNGRADED")
        rows.append({"case_id": case.case_id, "changed": changed, "before": old, "after": new})
    data = {
        "form_policy_id": form_policy[1] if form_policy is not None else None,
        "base_version_id": base.version_id,
        "candidate_version_id": candidate.version_id,
        "base_revision": base.revision,
        "engine_build_id": engine_build_id(),
        "policy": policy.model_dump(mode="json"),
        "suite_hash": canonical_hash(
            [
                case.model_dump(
                    mode="json",
                    exclude={
                        "synthetic",
                        "merchant_id",
                        "expected_verdict",
                    },
                )
                for case in cases
            ]
        ),
        "sample_count": len(cases),
        "changed_case_count": sum(bool(row["changed"]) for row in rows),
        "transitions": transitions,
        "rule_changes": [change.model_dump(mode="json") for change in changes],
        "cases": rows,
        "risks": sorted(risks),
    }
    return ImpactReport(**data, report_hash=canonical_hash(data))
