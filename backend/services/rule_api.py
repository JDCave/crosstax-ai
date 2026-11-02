"""API facade delegates all validation and persistence to engine services."""

from functools import lru_cache

from backend.api.schemas.rule_engine import CoverageEntry, CoverageResponse, RuleVersionResponse
from backend.engine.audit_service import AuditValidationService
from backend.engine.contracts import AuditIssue, CRSFormData, ValidationPolicy, ValidationResult
from backend.engine.rule_loader import RuleLoader, RuleSnapshot
from backend.engine.validation import ValidationEngine
from backend.infrastructure.database import async_session_factory
from backend.infrastructure.exceptions import AppException, ConflictException, NotFoundException
from backend.models import RuleAuditRecord


class RuleAPIService:
    def __init__(self, audit: AuditValidationService) -> None:
        self.audit = audit

    async def validate(
        self, session_id: str, form: CRSFormData, policy: ValidationPolicy, issues: list[AuditIssue]
    ) -> ValidationResult:
        try:
            return await self.audit.validate_and_store(session_id, form, policy, issues)
        except NotFoundException as exc:
            raise AppException(503, "NO_ACTIVE_RULES", "No active rule version is available") from exc

    async def result(self, session_id: str) -> ValidationResult:
        async with self.audit.sessions() as session:
            record = await session.get(RuleAuditRecord, session_id)
            if record is None:
                raise NotFoundException("Validation result not found")
            return ValidationResult.model_validate(record.result)

    async def replay(self, session_id: str) -> ValidationResult:
        try:
            return await self.audit.replay_stored(session_id)
        except ValueError as exc:
            raise ConflictException(
                "Historical validation cannot be replayed with the available input, rules or engine build"
            ) from exc

    async def snapshot(self) -> RuleSnapshot:
        try:
            return await self.audit.engine.loader.refresh()
        except NotFoundException as exc:
            raise AppException(503, "NO_ACTIVE_RULES", "No active rule version is available") from exc

    async def current(self) -> RuleVersionResponse:
        snapshot = await self.snapshot()
        return RuleVersionResponse(
            rule_version_id=snapshot.version_id,
            revision=snapshot.revision,
            rule_count=len(snapshot.variants) or len(snapshot.rules),
        )

    async def coverage(self) -> CoverageResponse:
        snapshot = await self.snapshot()
        rules = [
            CoverageEntry(
                jurisdiction_code=key[0],
                holder_type=key[1],
                tin_type=key[2],
                rule_id=rule.rule_id,
                verification_level=rule.verification_level,
                source_url=rule.source_url,
                algorithm_source_url=rule.algorithm_source_url,
            )
            for key, rule in snapshot.variants.items()
        ]
        rules.extend(
            CoverageEntry(
                jurisdiction_code=code,
                holder_type=None,
                tin_type=None,
                rule_id=rule.rule_id,
                verification_level="FORMAT_ONLY" if rule.algorithm == "REGEX_ONLY" else "CHECKSUM",
                source_url=rule.source_url,
                algorithm_source_url=rule.algorithm_source_url,
            )
            for code, rule in snapshot.rules.items()
        )
        return CoverageResponse(rule_version_id=snapshot.version_id, revision=snapshot.revision, rules=rules)


@lru_cache(maxsize=1)
def get_rule_api_service() -> RuleAPIService:
    return RuleAPIService(AuditValidationService(ValidationEngine(RuleLoader(async_session_factory))))
