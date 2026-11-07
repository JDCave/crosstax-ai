"""Structured D3 input models aligned with the upstream CRS contract."""

from __future__ import annotations

from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StructuredModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    non_nullable: ClassVar[set[str]] = set()

    @model_validator(mode="before")
    @classmethod
    def reject_explicit_null(cls, value: Any) -> Any:
        if isinstance(value, dict) and any(key in value and value[key] is None for key in cls.non_nullable):
            raise ValueError("Explicit null is not allowed for this field")
        return value


class FormData(StructuredModel):
    document: Document
    holder_type: Literal["INDIVIDUAL", "ENTITY", "CONTROLLING_PERSON"]
    name: Name
    birth_date: str | None = None
    birth_place: str | None = None
    hk_identity: HkIdentity | None = None
    entity: Entity | None = None
    addresses: list[Address] = Field(min_length=1, max_length=2)
    tax_residencies: list[TaxResidency] = Field(min_length=1)
    controlling_person: ControllingPerson | None = None
    declaration: Declaration
    non_nullable = {
        "addresses",
        "name",
        "controlling_person",
        "declaration",
        "hk_identity",
        "document",
        "holder_type",
        "entity",
        "tax_residencies",
    }


class Document(StructuredModel):
    is_encrypted: bool
    structure_tree_available: bool
    holders_declared: int = Field(ge=1)
    has_continuation_sheets: bool = False
    fingerprint: str | None = None
    non_nullable = {
        "holders_declared",
        "is_encrypted",
        "fingerprint",
        "has_continuation_sheets",
        "structure_tree_available",
    }


class Name(StructuredModel):
    title: str | None = None
    last_name: str | None = None
    first_name: str | None = None
    middle_names: list[str] = Field(default_factory=list)
    entity_legal_name: str | None = None
    is_branch: bool = False
    non_nullable = {"middle_names", "is_branch"}


class HkIdentity(StructuredModel):
    hkid_or_passport: str | None = None
    business_registration_number: str | None = None
    non_nullable = set()


class Entity(StructuredModel):
    incorporation_jurisdiction: str | None = None
    incorporation_jurisdiction_source: Literal["FORM", "MERCHANT_KYC", "BOTH_AGREE", "BOTH_CONFLICT"] | None = None
    entity_type: Literal["FINANCIAL_INSTITUTION", "ACTIVE_NFE", "PASSIVE_NFE"] | None = None
    entity_type_subitem: EntitySubitem | None = None
    controlling_person_names: list[str] = Field(default_factory=list)
    no_natural_person_control: bool = False
    poe_jurisdiction: str | None = None
    non_nullable = {"no_natural_person_control", "incorporation_jurisdiction_source", "controlling_person_names"}


class Address(StructuredModel):
    type: Literal["RESIDENCE", "MAILING"]
    line1: str | None = None
    city: str | None = None
    subentity: str | None = None
    country: str
    post_code: str | None = None
    source_layout_anomaly: str | None = None
    non_nullable = {"country", "type"}


class TaxResidency(StructuredModel):
    jurisdiction: str
    basis: Literal["RESIDENCE", "POEM"]
    tin: str | None = None
    no_tin_reason: Literal["A", "B", "C"] | None = None
    reason_b_explanation: str | None = None
    reason_c_applicability_unverified: bool = True
    non_nullable = {"reason_c_applicability_unverified", "basis", "jurisdiction"}


class ControllingPerson(StructuredModel):
    controlled_entities: list[ControlledEntity] = Field(default_factory=list, min_length=1, max_length=3)
    non_nullable = {"controlled_entities"}


class Declaration(StructuredModel):
    holder_or_authorized_resolved: bool
    signatory_name: str | None = None
    capacity: str | None = None
    power_of_attorney_attached: bool = False
    has_signature: bool
    signing_date: str | None = None
    non_nullable = {"holder_or_authorized_resolved", "power_of_attorney_attached", "has_signature"}


class ControlledEntity(StructuredModel):
    entity_name: str
    linked_document_ref: str | None = None
    link_confidence: Literal["HIGH", "LOW", "NAME_DOB_ONLY", "UNLINKED"] | None
    cp_types: list[str] = Field(default_factory=list)
    non_nullable = {"entity_name", "cp_types"}


class EntitySubitem(StructuredModel):
    regularly_traded_on: str | None = None
    related_entity_of: str | None = None
    specify: str | None = None
    non_nullable = set()


for _model in (
    FormData,
    Document,
    Name,
    HkIdentity,
    Entity,
    Address,
    TaxResidency,
    ControllingPerson,
    Declaration,
    ControlledEntity,
    EntitySubitem,
):
    _model.model_rebuild()
