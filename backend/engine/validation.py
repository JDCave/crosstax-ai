"""Public rule engine entry; called by the existing audit pipeline."""

import logging
from collections.abc import Sequence
from time import perf_counter

from backend.engine.completeness import check_completeness
from backend.engine.contracts import (
    AuditIssue,
    CRSFormData,
    ExecutionContext,
    TINCheck,
    ValidationPolicy,
    ValidationResult,
)
from backend.engine.regulatory_parameters import load_form_policy
from backend.engine.reproducibility import engine_build_id, input_fingerprint
from backend.engine.rule_loader import RuleLoader, RuleSnapshot, compile_snapshot
from backend.engine.tin_validator import TINValidatorEngine
from backend.engine.verdict import resolve_verdict
from backend.models import RuleVersion

logger = logging.getLogger(__name__)


class ValidationEngine:
    def __init__(self, loader: RuleLoader) -> None:
        self.loader = loader
        self.tin_validator = TINValidatorEngine()

    async def validate(
        self, form: CRSFormData, policy: ValidationPolicy, indicia_issues: Sequence[AuditIssue] = ()
    ) -> ValidationResult:
        try:
            snapshot = await self.loader.refresh()
        except Exception as exc:
            logger.warning("rule_load_failed", extra={"error_type": type(exc).__name__})
            raise
        return self.validate_snapshot(form, policy, snapshot, indicia_issues)

    def validate_snapshot(
        self,
        form: CRSFormData,
        policy: ValidationPolicy,
        snapshot: RuleSnapshot,
        indicia_issues: Sequence[AuditIssue] = (),
    ) -> ValidationResult:
        started = perf_counter()
        form_issues = check_completeness(form, policy, load_form_policy()[0]["reason_b_min_length"])
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
        result = ValidationResult(
            rule_version_id=snapshot.version_id,
            rule_revision=snapshot.revision,
            execution=ExecutionContext(
                engine_build_id=engine_build_id(),
                input_fingerprint=input_fingerprint(form, policy, indicia_issues),
                policy=policy,
            ),
            tin_check=tin_check,
            form_issues=tuple(form_issues),
            indicia_issues=tuple(indicia_issues),
            verdict=resolve_verdict(all_issues),
        )
        logger.info(
            "rule_validation_completed",
            extra={
                "rule_version_id": snapshot.version_id,
                "rule_revision": snapshot.revision,
                "verdict": result.verdict,
                "issue_count": len(all_issues),
                "duration_ms": round((perf_counter() - started) * 1000, 3),
            },
        )
        return result

    async def replay(
        self, form: CRSFormData, original: ValidationResult, indicia_issues: Sequence[AuditIssue] = ()
    ) -> ValidationResult:
        """Replay the historical version, never the currently active rules."""
        context = original.execution
        if context is None:
            raise ValueError("Historical result has no execution context")
        if context.engine_build_id != engine_build_id():
            raise ValueError("Engine build differs; use the archived original build")
        if input_fingerprint(form, context.policy, indicia_issues) != context.input_fingerprint:
            raise ValueError("Replay input, policy or upstream issues differ")
        async with self.loader.sessions() as session:
            version = await session.get(RuleVersion, original.rule_version_id)
            if version is None:
                raise ValueError("Historical rule version is unavailable")
            if version.schema_version != version.rules.get("schema_version", 1):
                raise ValueError("Historical rule schema differs")
            snapshot = compile_snapshot(version.version_id, original.rule_revision, version.rules)
        replayed = self.validate_snapshot(form, context.policy, snapshot, indicia_issues)
        if replayed != original:
            raise ValueError("Replayed result differs from stored result")
        return replayed
