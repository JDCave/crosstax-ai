"""Validated engine input and output contracts."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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
    holder_name: str = Field(min_length=1)
    holder_dob: str
    residence_address: str = Field(min_length=1)
    jurisdiction_code: str = Field(pattern=r"^[A-Z]{2}$")
    tin: str | None = None
    has_no_tin: bool
    tin_reason_code: Literal["A", "B", "C"] | None = None
    tin_reason_explanation: str | None = None
    has_signature: bool
    signing_date: str | None = None


class ValidationPolicy(BaseModel):
    """Caller supplies the business date and any agreed historical cutoff."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    today: date
    earliest_signing_date: date | None = None


class ValidationResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    rule_version_id: str
    rule_revision: int
    form_issues: tuple[AuditIssue, ...]
    indicia_issues: tuple[AuditIssue, ...]
    verdict: Literal["AUTO_PASS", "NEED_USER_FIX", "MANUAL_TRIAGE"]
