"""Public rule engine entry; called by the existing audit pipeline."""

from collections.abc import Sequence

from backend.engine.completeness import check_completeness
from backend.engine.contracts import AuditIssue, CRSFormData, TINCheck, ValidationPolicy, ValidationResult
from backend.engine.rule_loader import RuleLoader, RuleSnapshot
from backend.engine.tin_validator import TINValidatorEngine
from backend.engine.verdict import resolve_verdict


class ValidationEngine:
    def __init__(self, loader: RuleLoader) -> None:
        self.loader = loader
        self.tin_validator = TINValidatorEngine()

    async def validate(
        self, form: CRSFormData, policy: ValidationPolicy, indicia_issues: Sequence[AuditIssue] = ()
    ) -> ValidationResult:
        snapshot = await self.loader.refresh()
        return self.validate_snapshot(form, policy, snapshot, indicia_issues)

    def validate_snapshot(
        self,
        form: CRSFormData,
        policy: ValidationPolicy,
        snapshot: RuleSnapshot,
        indicia_issues: Sequence[AuditIssue] = (),
    ) -> ValidationResult:
        form_issues = check_completeness(form, policy)
        if not form.has_no_tin:
            form_issues.extend(
                self.tin_validator.validate(form.tin, form.jurisdiction_code, snapshot, form.holder_type, form.tin_type)
            )
        tin_check = (
            TINCheck(status="NOT_APPLICABLE", verification_level="NONE")
            if form.has_no_tin
            else self.tin_validator.trace(form.tin, form.jurisdiction_code, snapshot, form.holder_type, form.tin_type)
        )
        all_issues = [*form_issues, *indicia_issues]
        return ValidationResult(
            rule_version_id=snapshot.version_id,
            rule_revision=snapshot.revision,
            tin_check=tin_check,
            form_issues=tuple(form_issues),
            indicia_issues=tuple(indicia_issues),
            verdict=resolve_verdict(all_issues),
        )
