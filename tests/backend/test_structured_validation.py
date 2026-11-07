"""Validate the upstream structured contract through actual HTTP calls."""

import json
from pathlib import Path

from tests.backend import test_rule_engine_api as api_fixtures

api_client = api_fixtures.api_client

URL = "/api/v1/rule-engine/validate"


def request(kind="individual"):
    return json.loads(Path(f"assets/crs-templates/crs-structured-{kind}-request.json").read_text())


async def test_structured_individual_accepts_encrypted_document_and_normalizes_dates(api_client):
    client, _ = api_client
    response = await client.post(URL, json=request())
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["verdict"] == "AUTO_PASS"
    assert result["checks"] is None and result["residence_results"][0]["checks"]["status"] == "PASSED"
    assert result["execution"]["form_policy_id"]
    assert "A123456" not in response.text and "1990-05-20" not in response.text


async def test_separate_identity_and_address_required_fields_are_checked(api_client):
    client, _ = api_client
    body = request()
    body["form_data"]["name"]["last_name"] = None
    body["form_data"]["addresses"][0]["city"] = None
    response = await client.post(URL, json=body)
    assert response.status_code == 200
    result = response.json()
    assert result["verdict"] == "NEED_USER_FIX"
    assert {"name.last_name", "addresses.0.city"} <= {i["field"] for i in result["issues"]}
    body = request()
    body["form_data"]["birth_place"] = None
    assert (await client.post(URL, json=body)).json()["verdict"] == "AUTO_PASS"


async def test_hk_derived_equality_identifies_both_source_paths(api_client):
    client, _ = api_client
    body = request()
    body["form_data"]["hk_identity"]["hkid_or_passport"] = "B1234567"
    result = (await client.post(URL, json=body)).json()
    issue = next(i for i in result["issues"] if i["code"] == "HK_TIN_IDENTITY_MISMATCH")
    assert issue["field"] == "tax_residencies.0.tin"
    assert "hk_identity.hkid_or_passport" in issue["message"]
    assert result["verdict"] == "NEED_USER_FIX"
    assert result["residence_results"][0]["checks"]["status"] == "FAILED"


async def test_more_than_twenty_rows_do_not_mean_multiple_holders(api_client):
    client, _ = api_client
    body = request()
    body["form_data"]["tax_residencies"] *= 21
    result = (await client.post(URL, json=body)).json()
    assert len(result["residence_results"]) == 21 and result["verdict"] == "AUTO_PASS"
    body["form_data"]["document"]["holders_declared"] = 2
    result = (await client.post(URL, json=body)).json()
    assert result["verdict"] == "NEED_USER_FIX"
    assert result["issues"][0]["code"] == "MULTI_HOLDER_DOCUMENT"
    assert result["residence_results"] == []


async def test_entity_and_controlling_person_are_preserved_and_not_falsely_verified(api_client):
    client, _ = api_client
    entity = request("entity")
    result = (await client.post(URL, json=entity)).json()
    assert result["verdict"] == "MANUAL_TRIAGE"
    assert any(i["code"] == "CROSS_DOCUMENT_VERIFICATION_REQUIRED" for i in result["issues"])
    entity["form_data"]["entity"]["controlling_person_names"] = []
    assert (await client.post(URL, json=entity)).json()["verdict"] == "NEED_USER_FIX"
    cp = request("controlling-person")
    response = await client.post(URL, json=cp)
    assert response.status_code == 200, response.text
    assert response.json()["verdict"] == "MANUAL_TRIAGE"
    assert any(i["code"] == "UNCONFIRMED_ENTITY_LINK" for i in response.json()["issues"])


async def test_poem_exemption_and_layout_anomaly_remain_explicit_review_cases(api_client):
    client, _ = api_client
    body = request("entity")
    body["form_data"]["tax_residencies"][0].update(basis="POEM", tin=None)
    result = (await client.post(URL, json=body)).json()
    assert any(i["code"] == "POEM_REVIEW_REQUIRED" for i in result["issues"])
    assert result["residence_results"][0]["checks"]["status"] == "NOT_APPLICABLE"
    body = request()
    body["form_data"]["tax_residencies"][0].update(tin=None, no_tin_reason="C", reason_c_applicability_unverified=False)
    result = (await client.post(URL, json=body)).json()
    assert result["verdict"] == "MANUAL_TRIAGE"
    assert any(i["code"] == "EXEMPTION_REVIEW_REQUIRED" for i in result["issues"])
    body = request()
    body["form_data"]["addresses"][0]["source_layout_anomaly"] = "duplicate Line 2"
    assert (await client.post(URL, json=body)).json()["verdict"] == "MANUAL_TRIAGE"


async def test_declared_authorization_signature_and_dates_are_deterministic(api_client):
    client, _ = api_client
    body = request()
    body["form_data"]["declaration"].update(
        holder_or_authorized_resolved=False, has_signature=False, signing_date="31/02/2026"
    )
    result = (await client.post(URL, json=body)).json()
    assert {"UNRESOLVED_DECLARATION", "NO_SIGNATURE", "INVALID_DATE"} <= {i["code"] for i in result["issues"]}
    assert result["verdict"] == "NEED_USER_FIX"


async def test_unknown_fields_are_rejected_without_leaking_values(api_client):
    client, _ = api_client
    body = request()
    body["form_data"]["name"]["unknown"] = "PRIVATE INPUT"
    response = await client.post(URL, json=body)
    assert response.status_code == 422 and "PRIVATE INPUT" not in response.text


async def test_many_review_issues_do_not_break_core_result_when_guidance_requested(api_client):
    client, _ = api_client
    body = request()
    body["form_data"]["tax_residencies"] = [{"jurisdiction": "IS", "basis": "RESIDENCE", "tin": "12345678"}] * 310
    body["include_guidance"] = True
    response = await client.post(URL, json=body)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["verdict"] == "MANUAL_TRIAGE"
    assert result["guidance"]["status"] == "FALLBACK"
    assert result["guidance"]["omitted_action_count"] == 10
    assert len(result["guidance"]["actions"]) == 300 and len(result["issues"]) == 310


async def test_normalized_dates_have_the_same_execution_identity(api_client):
    client, _ = api_client
    dmy = request()
    iso = request()
    iso["form_data"]["birth_date"] = "1990-05-20"
    iso["form_data"]["declaration"]["signing_date"] = "2026-11-04"
    first = (await client.post(URL, json=dmy)).json()
    second = (await client.post(URL, json=iso)).json()
    assert first["execution"]["input_fingerprint"] == second["execution"]["input_fingerprint"]


async def test_iso_codes_and_explicit_power_of_attorney_are_checked(api_client):
    client, _ = api_client
    body = request()
    body["form_data"]["addresses"][0]["country"] = "ZZ"
    result = (await client.post(URL, json=body)).json()
    assert any(i["code"] == "INVALID_ADDRESS_COUNTRY" for i in result["issues"])
    body = request("entity")
    body["form_data"]["declaration"]["capacity"] = "power of attorney"
    result = (await client.post(URL, json=body)).json()
    assert any(i["code"] == "MISSING_POWER_OF_ATTORNEY" for i in result["issues"])


def test_contract_model_field_sets_match_authoritative_schema():
    from backend.engine import structured_contracts as models

    schema = json.loads(Path(".specify/features/001-crs-contract/contracts/crs-form-data.schema.json").read_text())
    for name, definition in schema["$defs"].items():
        assert set(getattr(models, name).model_fields) == set(definition["properties"])


async def test_upstream_confirmed_reference_is_not_forced_into_low_confidence_review(api_client):
    client, _ = api_client
    body = request("controlling-person")
    body["form_data"]["controlling_person"]["controlled_entities"][0]["link_confidence"] = "HIGH"
    result = (await client.post(URL, json=body)).json()
    assert result["verdict"] == "AUTO_PASS"
    assert "cross_document_counterpart_verification" in result["review_scope"]["not_evaluated"]
    body["policy"]["today"] = 1794096000
    assert (await client.post(URL, json=body)).status_code == 422


def test_upgrade_impact_accepts_structured_samples_and_pins_form_policy():
    from backend.engine.contracts import ValidationPolicy
    from backend.engine.impact import analyze_impact
    from backend.engine.reproducibility import canonical_hash
    from backend.engine.rule_loader import RuleLoader, compile_snapshot
    from backend.engine.validation import ValidationEngine
    from backend.infrastructure.database import async_session_factory

    rules = json.loads(Path("rules/rules_global_v4.json").read_text())
    snapshot = compile_snapshot(canonical_hash(rules), 1, rules)
    body = request()
    report = analyze_impact(
        ValidationEngine(RuleLoader(async_session_factory)),
        snapshot,
        snapshot,
        [{"case_id": "STRUCTURED", "form_data": body["form_data"]}],
        ValidationPolicy.model_validate(body["policy"]),
    )
    assert report.form_policy_id
    assert not report.changed_case_count
    assert report.cases[0]["after"]["verdict"] == "AUTO_PASS"
