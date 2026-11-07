"""One synchronous validation request with optional grounded remediation."""

from collections.abc import Sequence
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Discriminator, Field, Tag, model_validator

from backend.agents.remediation import GuidanceResult
from backend.engine.contracts import AuditIssue, CRSFormData, ExecutionContext, TINCheck, ValidationPolicy
from backend.engine.document_contracts import (
    CheckItem,
    IssueOrigin,
    MultiResidenceForm,
    ResidenceResult,
    ReviewScope,
)
from backend.engine.structured_contracts import FormData, StructuredModel


def form_kind(value: Any) -> str:
    if isinstance(value, FormData) or (
        isinstance(value, dict) and bool({"document", "name", "declaration", "addresses"} & value.keys())
    ):
        return "structured"
    if isinstance(value, MultiResidenceForm) or (isinstance(value, dict) and "tax_residencies" in value):
        return "multi"
    return "single"


FormInput = Annotated[
    Annotated[CRSFormData, Tag("single")]
    | Annotated[MultiResidenceForm, Tag("multi")]
    | Annotated[FormData, Tag("structured")],
    Discriminator(form_kind),
]


class ValidationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    form_data: FormInput
    policy: ValidationPolicy
    indicia_issues: list[AuditIssue] = Field(default_factory=list, max_length=100)
    include_guidance: bool = Field(default=False, strict=True)

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
    residence_results: list[ResidenceResult]
    check_items: list[CheckItem]
    issue_origins: list[IssueOrigin]
    review_scope: ReviewScope
    guidance: GuidanceResult


class FieldError(BaseModel):
    field: str
    code: str
    message: str


class ErrorResponse(BaseModel):
    code: str
    message: str
    details: list[FieldError] | None = None


def field_errors(errors: Sequence[dict[str, Any]]) -> list[dict[str, str]]:
    """Keep safe schema paths, never input values, validator context or arbitrary field names."""
    from backend.engine.document_contracts import TaxResidence

    models: list[type[BaseModel]] = [
        ValidationRequest,
        CRSFormData,
        MultiResidenceForm,
        TaxResidence,
        ValidationPolicy,
        AuditIssue,
        FormData,
        *StructuredModel.__subclasses__(),
    ]
    known = {name for model in models for name in model.model_fields}
    known.update({"session_id", "deadline_at", "validation", "task_id", "Idempotency-Key"})
    messages = {
        "missing": "Required field is missing",
        "extra_forbidden": "Unknown field is not accepted",
        "json_invalid": "Malformed JSON",
        "bool_type": "Expected a JSON boolean",
        "value_error": "Field combination or policy is invalid",
    }
    details = []
    for error in errors[:20]:
        parts = [
            str(part) if isinstance(part, int) or part in known else "<unknown>"
            for part in error["loc"]
            if part not in ("body", "single", "multi", "structured")
        ]
        code = error["type"]
        detail = {
            "field": ".".join(parts) or "body",
            "code": code,
            "message": messages.get(code, "Invalid field type, format or allowed value"),
        }
        if detail not in details:
            details.append(detail)
    return details
