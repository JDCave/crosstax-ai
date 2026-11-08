"""Validated engine input and output contracts."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AuditIssue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)
    code: str
    severity: Literal["BLOCKER", "WARNING"]
    field: str | None = None
    message: str
    confidence: float = Field(ge=0, le=1)


class CRSFormData(BaseModel):
    """Dates remain strings so invalid signing dates become business issues."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    holder_name: str = Field(min_length=1, max_length=300)
    holder_dob: str | None = Field(default=None, max_length=32)
    incorporation_date: str | None = Field(default=None, max_length=32)
    residence_address: str = Field(min_length=1, max_length=2000)
    jurisdiction_code: str = Field(pattern=r"^[A-Z]{2}$")
    holder_type: Literal["INDIVIDUAL", "ENTITY"] | None = None
    tin_type: str | None = Field(default=None, max_length=100)
    tin: str | None = None
    has_no_tin: bool
    tin_reason_code: Literal["A", "B", "C"] | None = None
    tin_reason_explanation: str | None = Field(default=None, max_length=4000)
    has_signature: bool
    signing_date: str | None = Field(default=None, max_length=32)


class ValidationPolicy(BaseModel):
    """Caller supplies the business date and any agreed historical cutoff."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    today: date
    earliest_signing_date: date | None = None
    strict_coverage: bool = True

    @field_validator("today", "earliest_signing_date", mode="before")
    @classmethod
    def require_canonical_date(cls, value: Any) -> Any:
        if value is None or type(value) is date:
            return value
        if isinstance(value, str):
            parsed = date.fromisoformat(value)
            if parsed.isoformat() == value:
                return value
        raise ValueError("Policy date must be YYYY-MM-DD")


class TINCheck(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    status: Literal["PASSED", "FAILED", "NOT_COVERED", "NOT_APPLICABLE"]
    verification_level: Literal["FORMAT_ONLY", "CHECKSUM", "NONE"]
    rule_id: str | None = None
    source_url: str | None = None
    algorithm_source_url: str | None = None
    checks_performed: tuple[str, ...] = ()
    checks_not_performed: tuple[str, ...] = ()
    reason_code: str | None = None


class ExecutionContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    engine_build_id: str
    form_policy_id: str | None = None
    input_fingerprint: str
    policy: ValidationPolicy


class ValidationResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    rule_version_id: str
    rule_revision: int
    execution: ExecutionContext | None = None
    tin_check: TINCheck | None = None
    form_issues: tuple[AuditIssue, ...]
    indicia_issues: tuple[AuditIssue, ...]
    verdict: Literal["AUTO_PASS", "NEED_USER_FIX", "MANUAL_TRIAGE"]
