"""Transactional handoff for a teammate's existing audit pipeline."""

from collections.abc import Sequence

from sqlalchemy.exc import IntegrityError

from backend.engine.contracts import AuditIssue, CRSFormData, ValidationPolicy, ValidationResult
from backend.engine.validation import ValidationEngine
from backend.infrastructure.exceptions import ConflictException, NotFoundException
from backend.models import RuleAuditRecord


class AuditValidationService:
    def __init__(self, engine: ValidationEngine) -> None:
        self.engine = engine
        self.sessions = engine.loader.sessions

    async def validate_and_store(
        self,
        session_id: str,
        form: CRSFormData,
        policy: ValidationPolicy,
        upstream_issues: Sequence[AuditIssue] = (),
    ) -> ValidationResult:
        if not session_id.strip() or len(session_id) > 100:
            raise ValueError("Session ID is missing or oversized")
        # Retries return the original committed result even if active rules changed.
        from backend.engine.reproducibility import input_fingerprint

        fingerprint = input_fingerprint(form, policy, upstream_issues)
        async with self.sessions() as session:
            existing = await session.get(RuleAuditRecord, session_id)
            if existing is not None:
                if existing.input_fingerprint != fingerprint:
                    raise ConflictException("Session ID already belongs to different input")
                return ValidationResult.model_validate(existing.result)
        result = await self.engine.validate(form, policy, upstream_issues)
        try:
            async with self.sessions.begin() as session:
                session.add(
                    RuleAuditRecord(
                        session_id=session_id,
                        rule_version_id=result.rule_version_id,
                        input_fingerprint=fingerprint,
                        form_data=form.model_dump(mode="json"),
                        upstream_issues=[issue.model_dump(mode="json") for issue in upstream_issues],
                        result=result.model_dump(mode="json"),
                    )
                )
        except IntegrityError:
            async with self.sessions() as session:
                existing = await session.get(RuleAuditRecord, session_id)
                if existing is None:
                    raise
                if existing.input_fingerprint != fingerprint:
                    raise ConflictException("Concurrent session input conflict") from None
                return ValidationResult.model_validate(existing.result)
        return result

    async def replay_stored(self, session_id: str) -> ValidationResult:
        async with self.sessions() as session:
            record = await session.get(RuleAuditRecord, session_id)
            if record is None:
                raise NotFoundException("Stored validation record not found")
            form = CRSFormData.model_validate(record.form_data)
            upstream = [AuditIssue.model_validate(issue) for issue in record.upstream_issues]
            original = ValidationResult.model_validate(record.result)
        return await self.engine.replay(form, original, upstream)
