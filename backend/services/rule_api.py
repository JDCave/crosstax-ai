"""Stateless HTTP adapter: execute rules and return results without audit writes."""

from functools import lru_cache

from backend.api.schemas.rule_engine import ValidationResponse
from backend.engine.contracts import AuditIssue, CRSFormData, ValidationPolicy
from backend.engine.rule_loader import RuleLoader
from backend.engine.validation import ValidationEngine
from backend.infrastructure.database import async_session_factory
from backend.infrastructure.exceptions import AppException, NotFoundException


class RuleAPIService:
    def __init__(self, engine: ValidationEngine) -> None:
        self.engine = engine

    async def validate(
        self, form: CRSFormData, policy: ValidationPolicy, issues: list[AuditIssue]
    ) -> ValidationResponse:
        try:
            result = await self.engine.validate(form, policy, issues)
        except NotFoundException as exc:
            raise AppException(503, "NO_ACTIVE_RULES", "No active rule version is available") from exc
        return ValidationResponse(
            verdict=result.verdict,
            issues=[*result.form_issues, *result.indicia_issues],
            rule_version_id=result.rule_version_id,
            rule_revision=result.rule_revision,
            checks=result.tin_check,
            execution=result.execution,
        )


@lru_cache(maxsize=1)
def get_rule_api_service() -> RuleAPIService:
    return RuleAPIService(ValidationEngine(RuleLoader(async_session_factory)))
