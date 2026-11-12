"""T019 — User Story 3 acceptance scenarios: derived equalities run automatically (US3-AS1-AS4)."""

from __future__ import annotations

import json
from pathlib import Path

from tests.backend import test_rule_engine_api as api_fixtures

api_client = api_fixtures.api_client

URL = "/api/v1/rule-engine/validate"


def request(kind: str = "individual"):
    return json.loads(Path(f"assets/crs-templates/crs-structured-{kind}-request.json").read_text(encoding="utf-8"))


async def test_as1_individual_hkid_and_hk_tin_mismatch_names_both_field_positions(api_client):
    client, _ = api_client
    body = request()
    body["form_data"]["hk_identity"]["hkid_or_passport"] = "B123456(7)"
    result = (await client.post(URL, json=body)).json()
    issue = next(i for i in result["issues"] if i["code"] == "HK_TIN_IDENTITY_MISMATCH")
    assert issue["severity"] == "BLOCKER"
    assert "tax_residencies" in issue["field"]  # one source position is the TIN row
    assert "hk_identity.hkid_or_passport" in issue["message"]  # the other source position is quoted
    assert result["verdict"] == "NEED_USER_FIX"


async def test_as2_entity_br_number_and_hk_tin_mismatch_reported(api_client):
    client, _ = api_client
    body = request("entity")
    hk_rows = [r for r in body["form_data"]["tax_residencies"] if r["jurisdiction"] == "HK"]
    assert hk_rows, "entity sample must carry an HK residency row"
    hk_rows[0]["tin"] = "99999999"  # BR mismatch on purpose
    result = (await client.post(URL, json=body)).json()
    issue = next(i for i in result["issues"] if i["code"] == "HK_TIN_IDENTITY_MISMATCH")
    assert "business_registration_number" in issue["message"] or "hk_identity" in issue["field"]
    assert result["verdict"] in ("NEED_USER_FIX", "MANUAL_TRIAGE")


async def test_as3_poem_is_an_independent_declaration_not_a_residency_substitute(api_client):
    """FR-017: a fiscally transparent entity filing POEM is accepted as its own fact."""
    client, _ = api_client
    body = request("entity")
    body["form_data"]["entity"]["poe_jurisdiction"] = "KY"
    body["form_data"]["tax_residencies"].append({"jurisdiction": "KY", "basis": "POEM", "tin": None})
    result = (await client.post(URL, json=body)).json()
    poem = [r for r in result["residence_results"] if r["jurisdiction_code"] == "KY"]
    assert poem and poem[0]["checks"]["status"] == "NOT_APPLICABLE"  # POEM is not a TIN-verifiable residency
    assert poem[0]["checks"]["reason_code"] == "POEM_REVIEW_REQUIRED"
    codes = {i["code"] for i in result["issues"]}
    assert "POEM_REVIEW_REQUIRED" in codes  # kept explicit, never silently folded into residence facts


async def test_as4_reason_c_flagged_unverified_never_silent(api_client):
    """FR-020: applicability of reason C is a human-review marker, not an automatic pass."""
    client, _ = api_client
    body = request()
    body["form_data"]["tax_residencies"] = [
        {
            "jurisdiction": "KY", "basis": "RESIDENCE", "tin": None,
            "no_tin_reason": "C", "reason_c_applicability_unverified": False,
        }
    ]
    result = (await client.post(URL, json=body)).json()
    exemption = next(i for i in result["issues"] if i["code"] == "EXEMPTION_REVIEW_REQUIRED")
    assert exemption["severity"] == "WARNING"
    assert result["verdict"] != "AUTO_PASS"
