"""Cross-document linking (FR-045 / FR-025 / FR-027 / SC-010): entity <-> controlling-person forms.

The entity's controlling-person list and each CP form's controlled_entities back-reference are
linked with Ref. No. as the primary key and CP name + date of birth as corroborating signal.
Every automatically established link carries a confidence marker; LOW / NAME_DOB_ONLY / UNLINKED
MUST degrade to MANUAL_TRIAGE and MUST NOT be treated as confirmed (FR-045, structured contract
`link_confidence`, rules/hk/form_policy.json trusted_link_confidences).

SC-012 reverse-gate invariant lives here too: a declared entity with N controlling-person names
requires exactly N CP documents that back-reference it; more or fewer is a cross-document
quantity mismatch, never a silent pass.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Confidence = Literal["HIGH", "LOW", "NAME_DOB_ONLY", "UNLINKED"]
_UNTRUSTED = {"LOW", "NAME_DOB_ONLY", "UNLINKED"}


@dataclass(frozen=True)
class EntitySide:
    ref_no: str | None
    legal_name: str | None
    controlling_person_names: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ControllingPersonSide:
    cp_name: str | None
    cp_dob: str | None
    declared_entity_ref_no: str | None = None
    declared_entity_name: str | None = None


@dataclass(frozen=True)
class LinkResult:
    cp_name: str | None
    confidence: Confidence
    basis: str
    requires_manual_triage: bool


@dataclass(frozen=True)
class BundleVerdict:
    links: list[LinkResult]
    missing_cp_documents: list[str]
    unmatched_cps: list[str]
    triage_count: int
    quantity_mismatch: bool

    @property
    def verdict(self) -> Literal["AUTO_PASS", "NEED_USER_FIX", "MANUAL_TRIAGE"]:
        # BLOCKER-class quantity mismatch outranks WARNING-class unconfirmed links.
        if self.quantity_mismatch:
            return "NEED_USER_FIX"
        if self.triage_count:
            return "MANUAL_TRIAGE"
        return "AUTO_PASS"


def establish_link(entity: EntitySide, cp: ControllingPersonSide) -> LinkResult:
    """Ref. No. is the primary key; CP name (+ DOB) is the corroborating signal.

    HIGH requires BOTH the primary key and the corroborating signal to agree: the CP declares
    this entity's Ref. No. AND is present in the entity's controlling-person list. Ref No alone
    (person not corroborated) is a signal disagreement -> LOW, never a silent HIGH (FR-045).
    """
    ref_match = bool(entity.ref_no) and cp.declared_entity_ref_no == entity.ref_no
    name_set = {_normalized(n) for n in entity.controlling_person_names if n}
    name_match = cp.cp_name is not None and _normalized(cp.cp_name) in name_set
    dob_present = bool(cp.cp_dob)
    if ref_match and name_match:
        return LinkResult(cp.cp_name, "HIGH", "REF_NO_AND_NAME_AGREE", False)
    if ref_match:
        return LinkResult(cp.cp_name, "LOW", "REF_MATCH_NAME_NOT_CORROBORATED", True)
    if name_match and dob_present:
        return LinkResult(cp.cp_name, "NAME_DOB_ONLY", "NAME_DOB_FALLBACK_WITHOUT_REF", True)
    if name_match:
        return LinkResult(cp.cp_name, "LOW", "NAME_MATCH_WITHOUT_DOB", True)
    return LinkResult(cp.cp_name, "UNLINKED", "NO_SIGNAL_MATCHED", True)


def _normalized(name: str) -> str:
    return " ".join(name.split()).casefold()


def link_bundle(entity: EntitySide, cps: list[ControllingPersonSide]) -> BundleVerdict:
    links = [establish_link(entity, cp) for cp in cps]
    linked_names = {_normalized(link.cp_name or "") for link in links if link.confidence == "HIGH"}
    missing = [name for name in entity.controlling_person_names if _normalized(name) not in linked_names]
    declared_names = {_normalized(n) for n in entity.controlling_person_names if n}
    unmatched = [
        link.cp_name or "<unnamed>"
        for link in links
        if link.cp_name and _normalized(link.cp_name) not in declared_names and link.confidence != "HIGH"
    ]
    high_count = sum(1 for link in links if link.confidence == "HIGH")
    quantity_mismatch = bool(missing) or high_count > len(entity.controlling_person_names)
    return BundleVerdict(
        links=links,
        missing_cp_documents=missing,
        unmatched_cps=unmatched,
        triage_count=sum(1 for link in links if link.requires_manual_triage),
        quantity_mismatch=quantity_mismatch,
    )
