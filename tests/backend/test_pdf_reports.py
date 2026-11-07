"""Task-to-PDF HTTP flow, provenance, font embedding and resource/error boundaries."""

import asyncio
import hashlib
import json
import threading
from datetime import timedelta
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from pypdf import PdfReader

from backend.infrastructure.exceptions import AppException
from backend.infrastructure.rule_tasks import utcnow
from backend.models import RuleValidationTask
from backend.reports.renderer import ReportTooLarge
from backend.services.pdf_reports import PDFReportService, get_pdf_report_service
from tests.backend import test_rule_tasks as task_fixtures

api_client = task_fixtures.api_client
task_api = task_fixtures.task_api


@pytest.fixture
async def report_api(task_api):
    client, service, worker = task_api
    reports = PDFReportService(service)
    client._transport.app.dependency_overrides[get_pdf_report_service] = lambda: reports
    return client, service, worker, reports


async def completed(report_api, validation=None):
    client, _, worker, _ = report_api
    request = task_fixtures.payload()
    if validation:
        request["validation"] = validation
    submitted = await task_fixtures.submit(client, request)
    await worker.run_once()
    task = (await client.get(submitted.headers["Location"])).json()
    assert task["status"] == "SUCCEEDED", task
    assert task["report_url"].endswith("/report")
    return task


def extracted(content):
    reader = PdfReader(BytesIO(content))
    return reader, "\n".join(page.extract_text() for page in reader.pages)


async def test_complete_flow_pdf_matches_json_and_is_repeatable(report_api):
    client, service, _, _ = report_api
    request = json.loads(Path("assets/crs-templates/crs-structured-individual-request.json").read_text())
    request["form_data"]["name"]["first_name"] = "中文演示"
    task = await completed(report_api, request)
    with patch.object(service.api, "validate", AsyncMock(side_effect=AssertionError("must not rerun"))), patch.object(
        service.api.engine.loader, "refresh", AsyncMock(side_effect=AssertionError("must not refresh"))
    ):
        response = await client.get(task["report_url"], headers={"Origin": "http://localhost:5173"})
        again = await client.get(task["report_url"])
    assert response.status_code == 200, response.text[:100] if not response.content.startswith(b"%PDF") else ""
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert 'attachment; filename="crosstax-rule-report-' in response.headers["content-disposition"]
    assert "Content-Disposition" in response.headers["access-control-expose-headers"]
    assert response.headers["x-report-sha256"] == hashlib.sha256(response.content).hexdigest()
    assert again.content == response.content
    reader, text = extracted(response.content)
    assert "规则引擎校验报告" in text and "中文演示" in text
    assert task["task_id"] in text and task["session_id"] in text
    assert task["result"]["verdict"] in text
    assert task["result"]["execution"]["input_fingerprint"] in text.replace("\n", "")
    assert "not_evaluated" in text and "form_policy_id" in text
    assert "附录" in text and "原始" not in reader.metadata.title
    fonts = [font.get_object() for page in reader.pages for font in page["/Resources"]["/Font"].get_object().values()]
    assert any(font.get("/FontDescriptor") and font["/FontDescriptor"].get_object().get("/FontFile2") for font in fonts)


@pytest.mark.parametrize("case_index", [0, 1, 2, 3, 4])
async def test_all_demo_verdicts_export_without_ai(report_api, case_index):
    client, _, _, _ = report_api
    case = json.loads(Path("assets/mock-data/cases.json").read_text())[case_index]
    validation = task_fixtures.api_fixtures.payload() | {"form_data":case["form_data"], "indicia_issues":case["indicia_issues"]}
    task = await completed(report_api, validation)
    response = await client.get(task["report_url"])
    assert response.status_code == 200
    _, text = extracted(response.content)
    assert case["expected_verdict"] in text
    assert "未核实" in text


async def test_unknown_pending_failed_expired_and_corrupt_tasks(report_api):
    client, service, worker, _ = report_api
    assert (await client.get(f"/api/v1/rule-engine/tasks/{uuid4()}/report")).status_code == 404
    submitted = await task_fixtures.submit(client)
    location = submitted.headers["Location"]
    pending = await client.get(location + "/report")
    assert pending.status_code == 409 and pending.json()["code"] == "REPORT_NOT_READY"
    with patch.object(service.api, "validate_frozen", AsyncMock(side_effect=RuntimeError("private-secret"))):
        await worker.run_once()
    failed = await client.get(location + "/report")
    assert failed.status_code == 409 and failed.json()["code"] == "REPORT_TASK_FAILED"
    assert "private-secret" not in failed.text
    task = await completed(report_api)
    async with service.repository.sessions.begin() as session:
        row = await session.get(RuleValidationTask, task["task_id"])
        row.result_ciphertext = "corrupt-secret-marker"
    corrupt = await client.get(task["report_url"])
    assert corrupt.status_code == 503 and "corrupt-secret-marker" not in corrupt.text
    async with service.repository.sessions.begin() as session:
        row = await session.get(RuleValidationTask, task["task_id"])
        row.expires_at = utcnow() - timedelta(seconds=1)
    assert (await client.get(task["report_url"])).status_code == 410


async def test_html_is_data_and_long_fields_paginate(report_api):
    client, _, _, _ = report_api
    validation = task_fixtures.api_fixtures.payload()
    validation["form_data"] = validation["form_data"] | {
        "holder_name": '<img src="https://invalid.test/pixel"/> <b>中文</b>',
        "residence_address": "中文长地址" * 300,
    }
    task = await completed(report_api, validation)
    response = await client.get(task["report_url"])
    assert response.status_code == 200
    reader, text = extracted(response.content)
    assert '<img src="https://invalid.test/pixel"/>' in text
    assert "中文" in text and len(reader.pages) > 1


async def test_export_limits_and_renderer_failure_are_sanitized(report_api):
    client, _, _, _ = report_api
    task = await completed(report_api)
    with patch("backend.services.pdf_reports.render_report", side_effect=ReportTooLarge()):
        response = await client.get(task["report_url"])
    assert response.status_code == 413 and response.json()["code"] == "REPORT_TOO_LARGE"
    with patch("backend.services.pdf_reports.render_report", side_effect=RuntimeError("private-font-path")):
        response = await client.get(task["report_url"])
    assert response.status_code == 503 and "private-font-path" not in response.text


async def test_timeout_keeps_render_slot_until_thread_finishes(report_api):
    _, _, _, reports = report_api
    task = await completed(report_api)
    started, release = threading.Event(), threading.Event()
    reports.queue_timeout, reports.render_timeout = 0.02, 0.02

    def blocked(data):
        started.set()
        release.wait(2)
        return b"%PDF-test"

    try:
        with patch("backend.services.pdf_reports.render_report", blocked):
            with pytest.raises(AppException) as timeout:
                await reports.export(task["task_id"])
            assert timeout.value.code == "REPORT_TIMEOUT" and started.is_set()
            with pytest.raises(AppException) as busy:
                await reports.export(task["task_id"])
            assert busy.value.code == "REPORT_BUSY"
            release.set()
            await asyncio.gather(*reports._jobs)
            await asyncio.sleep(0)
            assert not reports._jobs
    finally:
        release.set()


async def test_not_ready_status_takes_priority_over_render_capacity(report_api):
    client, service, _, reports = report_api
    submitted = await task_fixtures.submit(client)
    url = submitted.headers["Location"] + "/report"
    await reports._slots.acquire()
    try:
        assert (await client.get(url)).json()["code"] == "REPORT_NOT_READY"
        claimed = await service.repository.claim()
        assert claimed.status == "RUNNING"
        response = await client.get(url)
        assert response.status_code == 409 and response.json()["code"] == "REPORT_NOT_READY"
    finally:
        reports._slots.release()


async def test_report_rejects_result_version_mismatch_and_expiry_during_render(report_api):
    client, service, _, _ = report_api
    task = await completed(report_api)
    async with service.repository.sessions.begin() as session:
        row = await session.get(RuleValidationTask, task["task_id"])
        data = service.cipher().decrypt(row.result_ciphertext)
        data["rule_revision"] += 1
        row.result_ciphertext = service.cipher().encrypt(data)
    response = await client.get(task["report_url"])
    assert response.status_code == 503 and response.json()["code"] == "REPORT_DATA_UNAVAILABLE"
    task = await completed(report_api)
    async with service.repository.sessions.begin() as session:
        row = await session.get(RuleValidationTask, task["task_id"])
        row.expires_at = utcnow() + timedelta(seconds=0.06)

    def delayed(data):
        import time
        time.sleep(0.1)
        return b"%PDF-test"

    with patch("backend.services.pdf_reports.render_report", delayed):
        assert (await client.get(task["report_url"])).status_code == 410


async def test_page_size_and_snapshot_limits_are_real_renderer_guards(report_api):
    client, _, _, _ = report_api
    task = await completed(report_api)
    for target, value in [("MAX_PAGES", 1), ("MAX_PDF_BYTES", 20), ("MAX_SNAPSHOT_BYTES", 20)]:
        with patch(f"backend.reports.renderer.{target}", value):
            response = await client.get(task["report_url"])
        assert response.status_code == 413 and response.json()["code"] == "REPORT_TOO_LARGE"
