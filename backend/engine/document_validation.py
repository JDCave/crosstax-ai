"""Evaluate all declared residences against exactly one immutable rule snapshot."""

from backend.engine.contracts import AuditIssue, CRSFormData, ExecutionContext, ValidationPolicy, ValidationResult
from backend.engine.document_contracts import CheckItem, IssueOrigin, MultiResidenceForm, ResidenceResult, ReviewScope
from backend.engine.reproducibility import canonical_hash, engine_build_id
from backend.engine.rule_loader import RuleSnapshot
from backend.engine.validation import ValidationEngine
from backend.engine.verdict import resolve_verdict

TAX_FIELDS = {"tin", "tin_type", "jurisdiction_code", "has_no_tin", "tin_reason_code", "tin_reason_explanation"}


class DocumentResult(ValidationResult):
    residence_results: list[ResidenceResult]
    check_items: list[CheckItem]
    issue_origins: list[IssueOrigin]
    review_scope: ReviewScope


def validate_document(
    engine: ValidationEngine,
    form: CRSFormData | MultiResidenceForm,
    policy: ValidationPolicy,
    snapshot: RuleSnapshot,
    upstream: list[AuditIssue],
) -> DocumentResult:
    multi = isinstance(form, MultiResidenceForm)
    if isinstance(form, MultiResidenceForm):
        common = form.model_dump(exclude={"tax_residencies"})
        forms = [CRSFormData(**common, **residence.model_dump()) for residence in form.tax_residencies]
    else:
        forms = [form]
    issues: list[AuditIssue] = []
    residences: list[ResidenceResult] = []
    first: ValidationResult | None = None
    for index, item in enumerate(forms):
        result = engine.validate_snapshot(item, policy, snapshot)
        if first is None:
            first = result
        indexes: list[int] = []
        for issue in result.form_issues:
            is_tax = issue.field in TAX_FIELDS
            if index and not is_tax:
                continue  # Common identity/signature/date checks belong to the document once.
            if multi and is_tax:
                issue = issue.model_copy(update={"field": f"tax_residencies.{index}.{issue.field}"})
            if is_tax:
                indexes.append(len(issues))
            issues.append(issue)
        assert result.tin_check is not None
        residences.append(
            ResidenceResult(
                index=index,
                jurisdiction_code=item.jurisdiction_code,
                checks=result.tin_check,
                issue_indexes=indexes,
            )
        )
    assert first is not None
    all_issues = [*issues, *upstream]
    origins = [
        IssueOrigin(issue_index=i, source="RULE_ENGINE" if i < len(issues) else "UPSTREAM", evidence_ref=f"issue:{i}")
        for i in range(len(all_issues))
    ]
    checks = []
    for check_id, field in [
        ("holder_name", "holder_name"),
        ("address", "residence_address"),
        ("birth_date", "holder_dob"),
        ("incorporation_date", "incorporation_date"),
        ("signature_presence", "has_signature"),
        ("signing_date", "signing_date"),
    ]:
        indexes = [i for i, issue in enumerate(issues) if issue.field == field]
        absent_optional = (field == "incorporation_date" and form.incorporation_date is None) or (
            field == "holder_dob" and form.holder_type == "ENTITY" and form.holder_dob is None
        )
        status = "FAILED" if indexes else "NOT_APPLICABLE" if absent_optional else "PASSED"
        checks.append(CheckItem(check_id=check_id, field=field, status=status, issue_indexes=indexes))
    for residence in residences:
        prefix = f"tax_residencies.{residence.index}" if multi else "tin"
        related = [all_issues[i] for i in residence.issue_indexes]
        status = (
            "FAILED" if any(i.severity == "BLOCKER" for i in related) else ("REVIEW_REQUIRED" if related else "PASSED")
        )
        checks.append(
            CheckItem(
                check_id=f"tax_residence:{residence.index}",
                field=prefix,
                status=status,
                issue_indexes=residence.issue_indexes,
            )
        )
    fingerprint = canonical_hash(
        {
            "form": form.model_dump(mode="json"),
            "policy": policy.model_dump(mode="json"),
            "indicia_issues": [issue.model_dump(mode="json") for issue in upstream],
        }
    )
    return DocumentResult(
        rule_version_id=snapshot.version_id,
        rule_revision=snapshot.revision,
        execution=ExecutionContext(engine_build_id=engine_build_id(), input_fingerprint=fingerprint, policy=policy),
        tin_check=None if multi else first.tin_check,
        form_issues=tuple(issues),
        indicia_issues=tuple(upstream),
        verdict=resolve_verdict(all_issues),
        residence_results=residences,
        check_items=checks,
        issue_origins=origins,
        review_scope=ReviewScope(),
    )
