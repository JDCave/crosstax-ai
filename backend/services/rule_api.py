"""Stateless HTTP adapter: one fixed snapshot, optional bounded AI, no audit writes."""

import asyncio
from functools import lru_cache
from typing import Any

from backend.agents.remediation import GuidanceSettings, RemediationAgent
from backend.api.schemas.rule_engine import ValidationResponse
from backend.engine.contracts import AuditIssue, CRSFormData, ValidationPolicy
from backend.engine.document_contracts import MultiResidenceForm
from backend.engine.document_validation import validate_document
from backend.engine.rule_loader import RuleLoader, RuleSnapshot
from backend.engine.structured_contracts import FormData
from backend.engine.structured_validation import validate_structured
from backend.engine.validation import ValidationEngine
from backend.infrastructure.database import async_session_factory
from backend.infrastructure.exceptions import AppException, NotFoundException


class RuleAPIService:
    def __init__(self, engine: ValidationEngine, agent: RemediationAgent | None = None) -> None:
        self.engine = engine
        self.agent = agent or RemediationAgent(GuidanceSettings())

    async def validate(
        self,
        form: CRSFormData | MultiResidenceForm | FormData,
        policy: ValidationPolicy,
        issues: list[AuditIssue],
        include_guidance: bool = False,
    ) -> ValidationResponse:
        try:
            snapshot = await self.engine.loader.refresh()
        except NotFoundException as exc:
            raise AppException(503, "NO_ACTIVE_RULES", "No active rule version is available") from exc
        return await self.validate_frozen(form, policy, issues, include_guidance, snapshot)

    async def validate_frozen(
        self,
        form: CRSFormData | MultiResidenceForm | FormData,
        policy: ValidationPolicy,
        issues: list[AuditIssue],
        include_guidance: bool,
        snapshot: RuleSnapshot,
        form_policy: tuple[dict[str, Any], str] | None = None,
        *,
        offload: bool = False,
    ) -> ValidationResponse:
        def compute() -> Any:
            return (
                validate_structured(form, policy, snapshot, issues, form_policy=form_policy)
                if isinstance(form, FormData)
                else (validate_document(self.engine, form, policy, snapshot, issues))
            )

        result = await asyncio.to_thread(compute) if offload else compute()
        guidance = await self.agent.generate(result, snapshot, include_guidance)
        return ValidationResponse(
            verdict=result.verdict,
            issues=[*result.form_issues, *result.indicia_issues],
            rule_version_id=result.rule_version_id,
            rule_revision=result.rule_revision,
            checks=result.tin_check,
            execution=result.execution,
            residence_results=result.residence_results,
            check_items=result.check_items,
            issue_origins=result.issue_origins,
            review_scope=result.review_scope,
            guidance=guidance,
        )


@lru_cache(maxsize=1)
def get_rule_api_service() -> RuleAPIService:
    return RuleAPIService(ValidationEngine(RuleLoader(async_session_factory)))
