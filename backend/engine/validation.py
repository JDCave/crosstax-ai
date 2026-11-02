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
        covered = form.jurisdiction_code in snapshot.rules or any(
            key[0] == form.jurisdiction_code for key in snapshot.variants
        )
        if form.has_no_tin:
            if not covered and (snapshot.variants or policy.strict_coverage):
                form_issues.append(
                    AuditIssue(
                        code="UNSUPPORTED_JURISDICTION",
                        severity="WARNING",
                        field="jurisdiction_code",
                        message="法域未覆盖。需要人工复核",
                        confidence=1.0,
                    )
                )
            form_issues.append(
                AuditIssue(
                    code="EXEMPTION_REVIEW_REQUIRED",
                    severity="WARNING",
                    field="tin_reason_code",
                    message="仅完成豁免声明完整性检查。适用性需要人工复核",
                    confidence=1.0,
                )
            )
        if form.has_no_tin:
            tin_check = TINCheck(
                status="NOT_APPLICABLE",
                verification_level="NONE",
                checks_performed=("exemption_declaration_completeness",),
                checks_not_performed=(
                    "exemption_applicability",
                    "format",
                    "checksum",
                    "issuance",
                    "ownership",
                    "tax_residency",
                ),
                reason_code="EXEMPTION_REVIEW_REQUIRED",
            )
        else:
            tin_issues, tin_check = self.tin_validator.evaluate(
                form.tin,
                form.jurisdiction_code,
                snapshot,
                form.holder_type,
                form.tin_type,
                strict_coverage=policy.strict_coverage,
            )
            form_issues.extend(tin_issues)
        all_issues = [*form_issues, *indicia_issues]
        return ValidationResult(
            rule_version_id=snapshot.version_id,
            rule_revision=snapshot.revision,
            tin_check=tin_check,
            form_issues=tuple(form_issues),
            indicia_issues=tuple(indicia_issues),
            verdict=resolve_verdict(all_issues),
        )
