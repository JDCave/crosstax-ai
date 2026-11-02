"""Stable JSON contract for the rule engine's internal service API."""

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.engine.contracts import AuditIssue, CRSFormData, ValidationPolicy, ValidationResult


class ValidationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$")
    form_data: CRSFormData
    policy: ValidationPolicy
    indicia_issues: list[AuditIssue] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def check_policy(self) -> "ValidationRequest":
        if self.policy.earliest_signing_date and self.policy.earliest_signing_date > self.policy.today:
            raise ValueError("Earliest signing date is later than business date")
        return self


class ValidationResponse(BaseModel):
    session_id: str
    result: ValidationResult


class CoverageEntry(BaseModel):
    jurisdiction_code: str
    holder_type: str | None
    tin_type: str | None
    rule_id: str | None
    verification_level: str
    source_url: str | None
    algorithm_source_url: str | None


class CoverageResponse(BaseModel):
    rule_version_id: str
    revision: int
    rules: list[CoverageEntry]


class RuleVersionResponse(BaseModel):
    rule_version_id: str
    revision: int
    rule_count: int


class ErrorResponse(BaseModel):
    code: str
    message: str
