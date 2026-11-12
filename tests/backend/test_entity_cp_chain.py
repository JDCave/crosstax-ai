"""T030 — User Story 5 chain tests (US5-AS1-AS7): classification -> conditional CP -> cross-doc links.

AS1/AS2 (Passive NFE conditional requirement, Active NFE exemption) run through the live
validation HTTP interface; AS4 (cross-document quantity) and AS5 (2-D matrix) use the linking
service; AS6/SC-006 (per-entity-form, effective-dated threshold, never a constant) uses the
regulatory-parameter evaluator; AS7 (senior managing official fallback) runs via the API.
"""

from __future__ import annotations

import json
from pathlib import Path

from backend.engine.regulatory_parameters import (
    evaluate_controlling_person_ratio,
    load_controlling_person_thresholds,
)
from backend.services.document_linking import ControllingPersonSide, EntitySide, establish_link, link_bundle
from tests.backend import test_rule_engine_api as api_fixtures

api_client = api_fixtures.api_client

URL = "/api/v1/rule-engine/validate"


def request(kind: str):
    return json.loads(Path(f"assets/crs-templates/crs-structured-{kind}-request.json").read_text(encoding="utf-8"))


# --- AS1 / AS2: conditional requirement through the live rule interface ------------------


async def test_us5_as1_passive_nfe_with_empty_cp_slots_is_blocker(api_client):
    client, _ = api_client
    body = request("entity")
    body["form_data"]["entity"]["entity_type"] = "PASSIVE_NFE"
    body["form_data"]["entity"]["controlling_person_names"] = []
    result = (await client.post(URL, json=body)).json()
    issue = next(i for i in result["issues"] if i["code"] == "MISSING_CONTROLLING_PERSON")
    assert issue["severity"] == "BLOCKER"
    assert result["verdict"] == "NEED_USER_FIX"


async def test_us5_as2_active_nfe_with_empty_cp_slots_is_legal(api_client):
    client, _ = api_client
    body = request("entity")
    body["form_data"]["entity"]["entity_type"] = "ACTIVE_NFE"
    body["form_data"]["entity"]["controlling_person_names"] = []
    result = (await client.post(URL, json=body)).json()
    assert all(i["code"] != "MISSING_CONTROLLING_PERSON" for i in result["issues"])


async def test_us5_as7_senior_managing_official_fallback_not_empty(api_client):
    """FR-024: no natural-person control is accepted only with a named senior official, never a blank."""
    client, _ = api_client
    body = request("entity")
    body["form_data"]["entity"]["entity_type"] = "PASSIVE_NFE"
    body["form_data"]["entity"]["no_natural_person_control"] = True
    body["form_data"]["entity"]["controlling_person_names"] = []
    result = (await client.post(URL, json=body)).json()
    assert any(i["code"] == "MISSING_CONTROLLING_PERSON" for i in result["issues"])


# --- AS4 / AS5: cross-document linking ----------------------------------------------------


def test_us5_as4_two_named_cps_require_exactly_two_back_referencing_cp_forms() -> None:
    entity = EntitySide(
        ref_no="REF-9",
        legal_name="ACME Ltd",
        controlling_person_names=["CHAN Tai Man", "LEE Xia"],
    )
    cps = [
        ControllingPersonSide("CHAN Tai Man", "1980-01-01", declared_entity_ref_no="REF-9"),
        ControllingPersonSide("LEE Xia", "1975-02-02", declared_entity_ref_no="REF-9"),
    ]
    verdict = link_bundle(entity, cps)
    assert not verdict.quantity_mismatch
    assert all(link.confidence == "HIGH" for link in verdict.links)
    assert verdict.verdict == "AUTO_PASS"
    missing_one = link_bundle(entity, cps[:1])
    assert missing_one.missing_cp_documents == ["LEE Xia"]
    assert missing_one.quantity_mismatch is True
    assert missing_one.verdict == "NEED_USER_FIX"


def test_fr045_ref_no_primary_key_with_name_dob_fallback_never_confirms_low() -> None:
    entity = EntitySide(ref_no="REF-9", legal_name="ACME", controlling_person_names=["CHAN Tai Man"])
    # name+DOB present but no Ref. No. -> NAME_DOB_ONLY, must degrade
    fallback = establish_link(entity, ControllingPersonSide("CHAN Tai Man", "1980-01-01", declared_entity_ref_no=None))
    assert fallback.confidence == "NAME_DOB_ONLY"
    assert fallback.requires_manual_triage is True
    # Ref No matches but the name is not a declared CP -> the two signals disagree -> LOW
    conflict = establish_link(entity, ControllingPersonSide("WONG Fei", "1990-03-03", declared_entity_ref_no="REF-9"))
    assert conflict.confidence == "LOW"
    assert conflict.requires_manual_triage is True


def test_unlinked_cp_degrades() -> None:
    entity = EntitySide(ref_no="REF-9", legal_name="ACME", controlling_person_names=["CHAN Tai Man"])
    orphans = establish_link(entity, ControllingPersonSide("NOBODY", None, declared_entity_ref_no="OTHER"))
    assert orphans.confidence == "UNLINKED"
    assert orphans.requires_manual_triage is True


def test_all_automatic_links_carry_a_confidence_marker_sc010() -> None:
    entity = EntitySide(ref_no="R", legal_name="L", controlling_person_names=["A", "B"])
    verdict = link_bundle(entity, [ControllingPersonSide("A", None, "R"), ControllingPersonSide("C", None, None)])
    assert all(link.confidence in {"HIGH", "LOW", "NAME_DOB_ONLY", "UNLINKED"} for link in verdict.links)


# --- AS6 / SC-006: per-entity-form, effective-dated threshold (never a constant) ----------


def test_thresholds_come_from_the_rule_file_not_python_constants() -> None:
    data, policy_id = load_controlling_person_thresholds()
    assert policy_id  # content hash identifies the exact reviewed bytes
    forms = {p["entity_form"]: p for p in data["parameters"]}
    assert forms["CORPORATION"]["threshold_ratio"] == 0.25
    assert forms["PARTNERSHIP"]["threshold_ratio"] == 0.0


def test_sc006_same_partnership_decides_differently_across_the_effective_date() -> None:
    """SC-006: entity form PARTNERSHIP flips between 2020-12-31 and 2021-01-01 (proves dates are live)."""
    data, _ = load_controlling_person_thresholds()
    params = data["parameters"]
    before_ratio, before_state = evaluate_controlling_person_ratio("PARTNERSHIP", "2020-12-31", params)
    after_ratio, after_state = evaluate_controlling_person_ratio("PARTNERSHIP", "2021-01-01", params)
    assert (before_state, before_ratio) == ("BEFORE_EFFECTIVE_FROM", None)
    assert (after_state, after_ratio) == ("APPLIED", 0.0)
    assert before_state != after_state  # a hardcoded constant could never produce this split


def test_unknown_entity_form_falls_back_to_manual_review_not_a_default() -> None:
    data, _ = load_controlling_person_thresholds()
    ratio, state = evaluate_controlling_person_ratio("SOLE_TRADER", "2021-01-01", data["parameters"])
    assert (ratio, state) == (None, "UNKNOWN_ENTITY_FORM")
    assert data["fallback"]["unknown_entity_form"] == "MANUAL_TRIAGE"


def test_entity_classification_criteria_file_loads_and_is_hashed() -> None:
    """T026: rules/hk/entity_classification.json is schema-gated; holder_type cannot substitute."""
    from backend.engine.regulatory_parameters import load_entity_classification

    data, criteria_id = load_entity_classification()
    assert criteria_id
    assert set(data["entity_types"]) == {"FINANCIAL_INSTITUTION", "ACTIVE_NFE", "PASSIVE_NFE"}
    assert data["exactly_one_hit"] is True
    assert "Investment entity" in data["entity_types"]["PASSIVE_NFE"]["ird_terms"]
