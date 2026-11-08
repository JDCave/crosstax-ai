"""Presentation contracts derived from immutable validation results."""

from typing import Literal

from pydantic import BaseModel


class RuleEvidence(BaseModel):
    jurisdiction_code: str
    rule_id: str | None
    source_url: str | None
    verification_level: str


class ExplanationCard(BaseModel):
    issue_index: int
    title: str
    severity: Literal["BLOCKER", "WARNING"]
    field: str | None
    reason: str
    action: str
    action_source: Literal["RULE", "AGENT"]
    origin: Literal["RULE_ENGINE", "UPSTREAM"]
    evidence_refs: list[str]
    rule_evidence: list[RuleEvidence]
    confidence: float


class FindingSummary(BaseModel):
    code: str
    field: str | None
    severity: str
    origin: str
    count: int


class TaskComparison(BaseModel):
    before_task_id: str
    after_task_id: str
    before_verdict: str
    after_verdict: str
    context: Literal["SAME_CONTEXT", "DIFFERENT_CONTEXT"]
    context_changes: list[str]
    changed_field_count: int
    changed_fields: list[str]
    changed_fields_truncated: bool
    resolved: list[FindingSummary]
    introduced: list[FindingSummary]
    remaining: list[FindingSummary]
    findings_truncated: bool
    statement: str
