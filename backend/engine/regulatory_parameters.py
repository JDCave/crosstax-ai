"""Regulatory parameter evaluation (FR-028 / FR-041): dates and entity forms, never constants.

Parameters load from rules/hk/ via the jurisdiction-file convention (rules/hk/README.md);
the evaluation applies a parameter only when business_date >= effective_from. Before that
date the value is NOT derivable and the caller must route to human review — an implicit
carry-back of the 2021 threshold to 2020 would silently mis-adjudicate (SC-006 proves the
split is real rather than a constant).
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.engine.reproducibility import canonical_hash
from backend.engine.rule_loader import load_jurisdiction_policy_file


class DerivedEquality(BaseModel):
    """One cross-field derived-equality rule (R32): jurisdiction + holder form -> source slot.

    Replaces the hardcoded HK special case (FR-041 debt, T031): the (jurisdiction, holder_type)
    -> (identity field, variant selector) mapping is data, not code. Codes follow
    <JUR>_IDENTITY_EVIDENCE_MISSING / <JUR>_TIN_IDENTITY_MISMATCH, so HK strings are unchanged.
    """

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    jurisdiction: str
    holder_type: Literal["INDIVIDUAL", "ENTITY", "CONTROLLING_PERSON"]
    source_field: str
    tin_type: str
    source: str = ""


class FormPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    schema_version: Literal[1]
    policy_revision_date: str
    source_kind: Literal["PROJECT_REQUIREMENT"]
    source_reference: str = Field(min_length=1)
    reason_b_min_length: int = Field(ge=1, le=4000)
    required_fields: dict[str, list[str]]
    entity_types: list[str] = Field(min_length=1)
    passive_entity_type: str
    trusted_link_confidences: list[str] = Field(min_length=1)
    country_codes: list[str] = Field(min_length=1)
    country_code_source: dict[str, str]
    poem_holder_types: list[str] = Field(min_length=1)
    power_of_attorney_capacities: list[str] = Field(min_length=1)
    declared_non_poa_capacities: list[str] = Field(min_length=1)
    derived_equalities: list[DerivedEquality] = Field(default_factory=list)

    @model_validator(mode="after")
    def complete_required_groups(self) -> FormPolicy:
        if set(self.required_fields) != {"INDIVIDUAL", "ENTITY", "CONTROLLING_PERSON"}:
            raise ValueError("Missing holder policy")
        if any(not fields or any(not path.strip() for path in fields) for fields in self.required_fields.values()):
            raise ValueError("Empty required-field policy")
        return self


def load_form_policy() -> tuple[dict[str, Any], str]:
    config, policy_id = load_jurisdiction_policy_file("hk", "form_policy", FormPolicy)
    date.fromisoformat(config["policy_revision_date"])  # Software policy revision, not a legal effective date.
    return config, policy_id


class ThresholdParameter(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    entity_form: Literal["CORPORATION", "PARTNERSHIP"]
    threshold_ratio: float = Field(ge=0, le=1)
    effective_from: str
    basis: str = ""
    source: str = ""
    semantics: str = ""


class ThresholdFile(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    schema_version: Literal[1]
    source_kind: str
    source_reference: str
    notes: str
    parameters: list[ThresholdParameter] = Field(min_length=1)
    fallback: dict[str, str]


class EntityClassificationFile(BaseModel):
    """Schema gate for rules/hk/entity_classification.json (FR-021/FR-022 criteria carrier)."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    schema_version: Literal[1]
    source_kind: str
    source_reference: str
    notes: str
    entity_types: dict[str, dict[str, Any]] = Field(min_length=3)
    exactly_one_hit: bool
    holder_type_substitution_prohibited: str

    def model_post_init(self, __context: Any) -> None:
        if not self.exactly_one_hit:
            raise ValueError("FR-021 requires exactly-one-hit classification")


def load_entity_classification() -> tuple[dict[str, Any], str]:
    return load_jurisdiction_policy_file("hk", "entity_classification", EntityClassificationFile)


def load_controlling_person_thresholds() -> tuple[dict[str, Any], str]:
    data, policy_id = load_jurisdiction_policy_file("hk", "controlling_person_thresholds", ThresholdFile)
    for parameter in data["parameters"]:
        date.fromisoformat(parameter["effective_from"])
    return data, policy_id


def evaluate_controlling_person_ratio(
    entity_form: str, business_date: str, parameters: list[dict[str, Any]]
) -> tuple[float | None, str]:
    """Return (ratio, state). state: APPLIED when the parameter covers form+date; otherwise the
    declared fallback — callers MUST NOT substitute a default constant (FR-028)."""
    try:
        today = date.fromisoformat(business_date)
    except ValueError:
        return None, "INVALID_DATE"
    for parameter in parameters:
        if parameter["entity_form"] != entity_form:
            continue
        if today >= date.fromisoformat(parameter["effective_from"]):
            return float(parameter["threshold_ratio"]), "APPLIED"
        return None, "BEFORE_EFFECTIVE_FROM"
    return None, "UNKNOWN_ENTITY_FORM"


def hash_parameters(parameters: list[dict[str, Any]]) -> str:
    return canonical_hash(parameters)
