"""One synchronous validation request and one flat result."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.engine.contracts import AuditIssue, CRSFormData, ExecutionContext, TINCheck, ValidationPolicy


class ValidationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    form_data: CRSFormData
    policy: ValidationPolicy
    indicia_issues: list[AuditIssue] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def check_policy(self) -> "ValidationRequest":
        if self.policy.earliest_signing_date and self.policy.earliest_signing_date > self.policy.today:
            raise ValueError("Earliest signing date is later than business date")
        return self


class ValidationResponse(BaseModel):
    verdict: Literal["AUTO_PASS", "NEED_USER_FIX", "MANUAL_TRIAGE"]
    issues: list[AuditIssue]
    rule_version_id: str
    rule_revision: int
    checks: TINCheck | None
    execution: ExecutionContext | None


class ErrorResponse(BaseModel):
    code: str
    message: str
