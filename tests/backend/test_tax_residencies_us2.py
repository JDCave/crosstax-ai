"""T017 — User Story 2 acceptance scenarios: one holder, many tax residencies (spec US2-AS1-AS4)."""

from __future__ import annotations

import json
from pathlib import Path

from tests.backend import test_rule_engine_api as api_fixtures

api_client = api_fixtures.api_client

URL = "/api/v1/rule-engine/validate"

def request():
    return json.loads(Path("assets/crs-templates/crs-structured-individual-request.json").read_text(encoding="utf-8"))

def base_residence(jurisdiction: str, **overrides):
    residence = {"jurisdiction": jurisdiction, "basis": "RESIDENCE", "tin": None}
    residence.update(overrides)
    return residence

async def test_as1_three_residencies_all_retained_and_each_adjudicated_independently(api_client):
    """US2-AS1: three jurisdictions survive; the no-TIN reason-B row is not a BLOCKER for lacking a TIN."""
    client, _ = api_client
    body = request()
    body["form_data"]["tax_residencies"] = [
        base_residence("HK", tin="A123456(3)"),
        base_residence("JP", tin="1234"),
        base_residence(
            "SG", no_tin_reason="B", reason_b_explanation="Singapore has not issued me a tax reference number yet"
        ),
    ]
    result = (await client.post(URL, json=body)).json()
    assert len(result["residence_results"]) == 3
    codes = [r["jurisdiction_code"] for r in result["residence_results"]]
    assert codes == ["HK", "JP", "SG"]
    blocker_tin_fields = {
        i["field"] for i in result["issues"] if i["severity"] == "BLOCKER" and i["code"] == "MISSING_TIN"
    }
    assert "tax_residencies.2.tin" not in blocker_tin_fields  # reason B exempts the TIN itself
    sg = next(r for r in result["residence_results"] if r["jurisdiction_code"] == "SG")
    assert sg["checks"]["status"] != "FAILED"  # at most REVIEW_REQUIRED (applicability), never BLOCKER for no-TIN

async def test_as2_six_residencies_are_not_truncated_to_five_printed_rows(api_client):
    """US2-AS2: six jurisdictions (beyond the five printed rows) all survive inside the 1 MiB body."""
    client, _ = api_client
    body = request()
    codes = ["HK", "JP", "SG", "GB", "DE", "AU"]
    tins = ["A123456(3)", "1234", "S1234567A", "1234567890", "12345678901", "12345678901"]
    body["form_data"]["tax_residencies"] = [base_residence(c, tin=t) for c, t in zip(codes, tins, strict=True)]
    result = (await client.post(URL, json=body)).json()
    assert [r["jurisdiction_code"] for r in result["residence_results"]] == codes

async def test_as3_reason_b_min_length_enforced_and_ac_never_require_explanation(api_client):
    """US2-AS3: reason B needs a stripped explanation of at least the configured length; A/C don't."""
    client, _ = api_client
    body = request()
    body["form_data"]["tax_residencies"] = [
        base_residence("HK", no_tin_reason="B", reason_b_explanation="   ab   "),  # too short even stripped
        base_residence("JP", no_tin_reason="A"),
        base_residence("SG", no_tin_reason="C"),
    ]
    result = (await client.post(URL, json=body)).json()
    missing = {i["field"] for i in result["issues"] if i["code"] == "MISSING_REASON"}
    assert "tax_residencies.0.reason_b_explanation" in missing
    assert not any(f.startswith("tax_residencies.1") or f.startswith("tax_residencies.2") for f in missing)

async def test_as4_tin_and_reason_coexist_reported_as_conflict_not_silently_chosen(api_client):
    """US2-AS4 / FR-015: TIN and no-TIN reason together MUST report the mutual-exclusion conflict."""
    client, _ = api_client
    body = request()
    body["form_data"]["tax_residencies"] = [
        base_residence("JP", tin="1234", no_tin_reason="B", reason_b_explanation="Both fields are filled deliberately")
    ]
    result = (await client.post(URL, json=body)).json()
    conflict = next(i for i in result["issues"] if i["code"] == "INCONSISTENT_TIN_DECLARATION")
    assert conflict["field"] == "tax_residencies.0.no_tin_reason"
    assert result["verdict"] == "NEED_USER_FIX"

async def test_each_residence_carries_its_own_verdict_not_one_flattened_result(api_client):
    """The D3 core: per-record adjudication was impossible under the single-value contract."""
    client, _ = api_client
    body = request()
    body["form_data"]["tax_residencies"] = [
        base_residence("HK", tin="A123456(3)"),
        base_residence("JP", tin="0000"),  # structurally failing TIN
    ]
    result = (await client.post(URL, json=body)).json()
    by_code = {r["jurisdiction_code"]: r for r in result["residence_results"]}
    assert len(result["residence_results"]) == 2
    assert {"HK", "JP"} <= set(by_code)
    assert by_code["HK"]["checks"]["status"] != by_code["JP"]["checks"]["status"]  # independent, not one shared verdict
