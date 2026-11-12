"""Deterministic CRS form completeness checks."""

from datetime import date

from backend.engine.contracts import AuditIssue, CRSFormData, ValidationPolicy


def check_completeness(form: CRSFormData, policy: ValidationPolicy, reason_b_min_length: int) -> list[AuditIssue]:
    """Deterministic legacy-path completeness checks.

    reason_b_min_length is supplied by the caller from rules/hk/form_policy.json (T031):
    the threshold is a regulatory parameter and MUST NOT live in Python (FR-041).
    """
    if policy.earliest_signing_date is not None and policy.earliest_signing_date > policy.today:
        raise ValueError("Earliest signing date cannot be later than business date")
    issues: list[AuditIssue] = []

    def add(code: str, field: str, message: str) -> None:
        issues.append(AuditIssue(code=code, severity="BLOCKER", field=field, message=message, confidence=1.0))

    for field, text in (("holder_name", form.holder_name), ("residence_address", form.residence_address)):
        if not text.strip():
            add("MISSING_FIELD", field, "必填字段不能只包含空白")
    # Entity incorporation dates are not present on the official CRS entity form.
    # Continue accepting the legacy holder_dob alias without requiring invented data.
    date_fields = [("holder_dob", form.holder_dob, form.holder_type != "ENTITY")]
    if form.incorporation_date is not None:
        date_fields.append(("incorporation_date", form.incorporation_date, False))
    for field, value, required in date_fields:
        if value is None and not required:
            continue
        try:
            holder_date = date.fromisoformat(value or "")
            if holder_date.isoformat() != value:
                raise ValueError("Noncanonical date")
        except ValueError:
            add("INVALID_DATE", field, "日期必须是有效的 YYYY-MM-DD 日期")
    if (
        form.holder_type == "ENTITY"
        and form.holder_dob
        and form.incorporation_date
        and form.holder_dob != form.incorporation_date
    ):
        add("INCONSISTENT_DATE", "incorporation_date", "成立日期与旧版日期字段不一致")
    if form.holder_type != "ENTITY" and form.incorporation_date is not None:
        add("UNEXPECTED_FIELD", "incorporation_date", "个人表单不适用成立日期")
    if form.has_no_tin and form.tin is not None and form.tin.strip():
        add("INCONSISTENT_TIN_DECLARATION", "has_no_tin", "已填写 TIN 与无 TIN 声明矛盾")
    if not form.has_no_tin and (form.tin_reason_code is not None or (form.tin_reason_explanation or "").strip()):
        add("INCONSISTENT_TIN_DECLARATION", "tin_reason_code", "已提供 TIN 时不应同时提交无 TIN 豁免理由")
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
        elif form.tin_reason_code == "B" and len((form.tin_reason_explanation or "").strip()) < reason_b_min_length:
            add(
                "MISSING_REASON",
                "tin_reason_explanation",
                f"Reason B 请提供至少 {reason_b_min_length} 个字符的解释",
            )
    return issues
