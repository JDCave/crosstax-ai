"""Multi-residence input and explainable document-level results."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.engine.contracts import TINCheck


class TaxResidence(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    jurisdiction_code: str = Field(pattern=r"^[A-Z]{2}$")
    tin_type: str | None = Field(default=None, max_length=100)
    tin: str | None = None
    has_no_tin: bool
    tin_reason_code: Literal["A", "B", "C"] | None = None
    tin_reason_explanation: str | None = Field(default=None, max_length=4000)


class MultiResidenceForm(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    holder_name: str = Field(min_length=1, max_length=300)
    holder_type: Literal["INDIVIDUAL", "ENTITY"]
    holder_dob: str | None = Field(default=None, max_length=32)
    incorporation_date: str | None = Field(default=None, max_length=32)
    residence_address: str = Field(min_length=1, max_length=2000)
    has_signature: bool
    signing_date: str | None = Field(default=None, max_length=32)
    tax_residencies: list[TaxResidence] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def unique_jurisdictions(self) -> "MultiResidenceForm":
        countries = [entry.jurisdiction_code for entry in self.tax_residencies]
        if len(countries) != len(set(countries)):
            raise ValueError("Duplicate tax residence jurisdiction")
        return self


class IssueOrigin(BaseModel):
    issue_index: int
    source: Literal["RULE_ENGINE", "UPSTREAM"]
    evidence_ref: str


class CheckItem(BaseModel):
    check_id: str
    field: str
    status: Literal["PASSED", "FAILED", "REVIEW_REQUIRED", "NOT_APPLICABLE"]
    issue_indexes: list[int] = Field(default_factory=list)


class ResidenceResult(BaseModel):
    index: int
    jurisdiction_code: str
    checks: TINCheck
    issue_indexes: list[int]


class ReviewScope(BaseModel):
    statement: str = "当前已执行检查通过不代表整份 CRS 合规或税收居民身份已经核实"
    evaluated: list[str] = Field(
        default_factory=lambda: [
            "required_identity_fields",
            "signature_presence_declaration",
            "date_format",
            "signing_date_policy",
            "tin_declaration_consistency",
            "configured_tin_rules",
        ]
    )
    not_evaluated: list[str] = Field(
        default_factory=lambda: [
            "tax_residency_determination",
            "tin_issuance_and_ownership",
            "signature_authenticity",
            "entity_classification",
            "controlling_persons",
            "completeness_of_declared_jurisdictions",
            "no_tin_exemption_applicability",
        ]
    )
