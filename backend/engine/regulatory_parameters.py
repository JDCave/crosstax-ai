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

from pydantic import BaseModel, ConfigDict, Field

from backend.engine.reproducibility import canonical_hash
from backend.engine.rule_loader import load_jurisdiction_policy_file


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
