"""Compare retained successful snapshots without exposing field values or rerunning rules."""

from collections import Counter
from typing import Any

from backend.api.schemas.presentation import FindingSummary, TaskComparison
from backend.api.schemas.rule_engine import ValidationResponse
from backend.api.schemas.rule_tasks import TaskResponse


def findings(result: ValidationResponse) -> Counter[tuple[str, str | None, str, str]]:
    origins = {item.issue_index: item.source for item in result.issue_origins}
    return Counter(
        (issue.code, issue.field, issue.severity, origins.get(i, "RULE_ENGINE"))
        for i, issue in enumerate(result.issues)
    )


def summaries(counter: Counter[tuple[str, str | None, str, str]]) -> list[FindingSummary]:
    return [
        FindingSummary(code=key[0], field=key[1], severity=key[2], origin=key[3], count=count)
        for key, count in sorted(counter.items(), key=lambda pair: str(pair[0]))[:200]
    ]


def compare_tasks(
    before: TaskResponse, after: TaskResponse, old: dict[str, Any], new: dict[str, Any]
) -> TaskComparison:
    assert before.result is not None and after.result is not None
    changes: list[str] = []
    changed_count = 0
    missing = object()

    def walk(left: Any, right: Any, path: str) -> None:
        nonlocal changed_count
        if type(left) is type(right) and isinstance(left, dict):
            for key in sorted(left.keys() | right.keys()):
                walk(left.get(key, missing), right.get(key, missing), f"{path}.{key}" if path else key)
        elif type(left) is type(right) and isinstance(left, list):
            for i in range(max(len(left), len(right))):
                walk(left[i] if i < len(left) else missing, right[i] if i < len(right) else missing, f"{path}.{i}")
        elif type(left) is not type(right) or left != right:
            changed_count += 1
            if len(changes) < 200:
                changes.append(path)

    walk(old, new, "")
    contexts = []
    for name, left, right in [
        ("RULE_VERSION", before.rule_version_id, after.rule_version_id),
        ("RULE_REVISION", before.rule_revision, after.rule_revision),
        ("TASK_BUILD", before.engine_build_id, after.engine_build_id),
        ("POLICY", old.get("policy"), new.get("policy")),
        ("UPSTREAM_FINDINGS", old.get("indicia_issues", []), new.get("indicia_issues", [])),
        (
            "EXECUTION_BUILD",
            before.result.execution.engine_build_id if before.result.execution else None,
            after.result.execution.engine_build_id if after.result.execution else None,
        ),
        (
            "FORM_POLICY",
            before.result.execution.form_policy_id if before.result.execution else None,
            after.result.execution.form_policy_id if after.result.execution else None,
        ),
    ]:
        if left != right:
            contexts.append(name)
    previous, current = findings(before.result), findings(after.result)
    removed, added, same = previous - current, current - previous, previous & current
    return TaskComparison(
        before_task_id=str(before.task_id),
        after_task_id=str(after.task_id),
        before_verdict=before.result.verdict,
        after_verdict=after.result.verdict,
        context="DIFFERENT_CONTEXT" if contexts else "SAME_CONTEXT",
        context_changes=contexts,
        changed_field_count=changed_count,
        changed_fields=changes,
        changed_fields_truncated=changed_count > 200,
        resolved=summaries(removed),
        introduced=summaries(added),
        remaining=summaries(same),
        findings_truncated=any(len(items) > 200 for items in [removed, added, same]),
        statement="执行上下文不同,不能仅归因于用户补正"
        if contexts
        else "同一执行上下文下的问题及输入变化;不证明未核实范围已通过",
    )
