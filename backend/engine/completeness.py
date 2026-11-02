"""Deterministic CRS form completeness checks."""

from datetime import date

from backend.engine.contracts import AuditIssue, CRSFormData, ValidationPolicy


def check_completeness(form: CRSFormData, policy: ValidationPolicy) -> list[AuditIssue]:
    if policy.earliest_signing_date is not None and policy.earliest_signing_date > policy.today:
        raise ValueError("Earliest signing date cannot be later than business date")
    issues: list[AuditIssue] = []

    def add(code: str, field: str, message: str) -> None:
        issues.append(AuditIssue(code=code, severity="BLOCKER", field=field, message=message, confidence=1.0))

    if not form.has_signature:
        add("NO_SIGNATURE", "has_signature", "请补充表单签名")
    try:
        signing_date = date.fromisoformat(form.signing_date or "")
        if signing_date.isoformat() != form.signing_date or signing_date > policy.today:
            raise ValueError("Invalid signing date")
        if policy.earliest_signing_date is not None and signing_date < policy.earliest_signing_date:
            raise ValueError("Signing date is too old")
    except ValueError:
        add("INVALID_DATE", "signing_date", "请填写有效的签署日期")
    if form.has_no_tin:
        if form.tin_reason_code is None:
            add("MISSING_REASON", "tin_reason_code", "无 TIN 时请选择 Reason A/B/C")
        elif form.tin_reason_code == "B" and len((form.tin_reason_explanation or "").strip()) < 5:
            add("MISSING_REASON", "tin_reason_explanation", "Reason B 请提供至少 5 个字符的解释")
    return issues
