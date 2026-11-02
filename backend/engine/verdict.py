"""Pure severity-based three-state resolution."""

from collections.abc import Iterable
from typing import Literal

from backend.engine.contracts import AuditIssue


def resolve_verdict(issues: Iterable[AuditIssue]) -> Literal["AUTO_PASS", "NEED_USER_FIX", "MANUAL_TRIAGE"]:
    severities = {issue.severity for issue in issues}
    if "BLOCKER" in severities:
        return "NEED_USER_FIX"
    if "WARNING" in severities:
        return "MANUAL_TRIAGE"
    return "AUTO_PASS"
