"""Durable task-to-report flow, stored downloads, state errors and worker recovery."""

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
from cryptography.fernet import Fernet
from pydantic import SecretStr
from pypdf import PdfReader
from sqlalchemy import delete, inspect

from backend.core.rule_reports import RuleReportSettings
from backend.infrastructure.rule_tasks import utcnow
from backend.models import RulePDFReport, RuleValidationTask
from backend.services.pdf_reports import PDFReportService, get_pdf_report_service
from backend.workers.pdf_reports import PDFReportWorker
from tests.backend import test_rule_tasks as task_fixtures

api_client = task_fixtures.api_client
task_api = task_fixtures.task_api


@pytest.fixture
async def report_api(task_api):
    client, service, worker = task_api
    reports = PDFReportService(service)
    client._transport.app.dependency_overrides[get_pdf_report_service] = lambda: reports
    return client, service, worker, reports


async def completed(report_api, validation=None, *, generate=True):
    client, service, worker, _ = report_api
    request = task_fixtures.payload()
    if validation:
        request["validation"] = validation
    submitted = await task_fixtures.submit(client, request)
    await worker.run_once()
    location = submitted.headers["Location"]
    task = (await client.get(location)).json()
    assert task["status"] == "SUCCEEDED" and task["report_status"] == "PENDING"
    assert task["result"] and task["report_url"] is None
    if generate:
        assert await PDFReportWorker(service).run_once()
        task = (await client.get(location)).json()
        assert task["report_status"] == "READY" and task["report_url"]
    return task


def url(task):
    return f"/api/v1/rule-engine/tasks/{task['task_id']}/report"


def extracted(content):
    reader = PdfReader(BytesIO(content))
    return reader, "\n".join(page.extract_text() for page in reader.pages)


async def test_completed_json_precedes_pdf_then_download_only_reads_artifact(report_api):
    client, service, _, reports = report_api
    validation = json.loads(
        Path("assets/crs-templates/crs-structured-individual-request.json").read_text(encoding="utf-8")
    )
    validation["form_data"]["name"]["first_name"] = "中文演示"
    task = await completed(report_api, validation, generate=False)
    generating = await client.get(url(task))
    assert generating.status_code == 409 and generating.json()["code"] == "REPORT_GENERATING"
    assert generating.headers["Retry-After"] == "2"
    assert await PDFReportWorker(service).run_once()
    metadata = await reports.repository.get(task["task_id"])
    assert "content_ciphertext" in inspect(metadata).unloaded
    stored = await reports.repository.get(task["task_id"], content=True)
    assert stored.status == "READY" and "%PDF" not in stored.content_ciphertext
    with patch("backend.workers.pdf_reports.render_report", side_effect=AssertionError("must not render")), patch.object(
        service.api.engine.loader, "refresh", AsyncMock(side_effect=AssertionError("must not refresh"))
    ):
        response = await client.get(url(task), headers={"Origin": "http://localhost:5173"})
        again = await client.get(url(task))
    assert response.status_code == 200 and response.content == again.content
    assert response.content == service.cipher().decrypt_pdf(stored.content_ciphertext)
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert 'attachment; filename="crosstax-rule-report-' in response.headers["content-disposition"]
    assert "Content-Disposition" in response.headers["access-control-expose-headers"]
    assert response.headers["x-report-sha256"] == hashlib.sha256(response.content).hexdigest() == stored.sha256
    reader, text = extracted(response.content)
    assert "规则引擎校验报告" in text and "中文演示" in text
    assert task["task_id"] in text and task["result"]["verdict"] in text
    assert task["result"]["execution"]["input_fingerprint"] in text.replace("\n", "")
    assert "not_evaluated" in text and "form_policy_id" in text and "附录" in text
    fonts = [font.get_object() for page in reader.pages for font in page["/Resources"]["/Font"].get_object().values()]
    assert any(font.get("/FontDescriptor") and font["/FontDescriptor"].get_object().get("/FontFile2") for font in fonts)
    # READY is immutable to automatic worker scans and survives a service restart/key rotation.
    service.settings.encryption_keys.insert(0, SecretStr(Fernet.generate_key().decode()))
    assert not await PDFReportWorker(service).run_once()
    assert (await PDFReportService(service).export(task["task_id"])).content == response.content


@pytest.mark.parametrize("case_index", [0, 1, 2, 3, 4])
async def test_all_business_verdicts_generate_and_export(report_api, case_index):
    client, _, _, _ = report_api
    case = json.loads(Path("assets/mock-data/cases.json").read_text(encoding="utf-8"))[case_index]
    validation = task_fixtures.api_fixtures.payload() | {"form_data":case["form_data"], "indicia_issues":case["indicia_issues"]}
    task = await completed(report_api, validation)
    response = await client.get(url(task))
    assert response.status_code == 200
    _, text = extracted(response.content)
    assert case["expected_verdict"] in text and "未核实" in text


async def test_unknown_pending_running_failed_and_expired_states(report_api):
    client, service, worker, _ = report_api
    assert (await client.get(f"/api/v1/rule-engine/tasks/{uuid4()}/report")).status_code == 404
    submitted = await task_fixtures.submit(client)
    location = submitted.headers["Location"]
    assert (await client.get(location + "/report")).json()["code"] == "REPORT_NOT_READY"
    claim = await service.repository.claim()
    assert (await client.get(location + "/report")).json()["code"] == "REPORT_NOT_READY"
    await service.repository.finish(claim.task_id, claim.claim_token, None, "TASK_EXECUTION_FAILED")
    assert (await client.get(location + "/report")).json()["code"] == "REPORT_TASK_FAILED"
    task = await completed(report_api)
    async with service.repository.sessions.begin() as session:
        row = await session.get(RuleValidationTask, task["task_id"])
        row.expires_at = utcnow() - timedelta(seconds=1)
    assert (await client.get(url(task))).status_code == 410
    reports = PDFReportWorker(service)
    assert await reports.repository.cleanup() == 1
    assert (await reports.repository.get(task["task_id"], content=True)).content_ciphertext is None


async def test_report_failure_is_independent_and_retries_are_bounded(report_api):
    client, service, _, _ = report_api
    task = await completed(report_api, generate=False)
    worker = PDFReportWorker(service, RuleReportSettings(_env_file=None, max_attempts=2))
    for attempt in range(2):
        with patch("backend.workers.pdf_reports.render_report", side_effect=RuntimeError("private-font-path")):
            await worker.run_once()
        state = await service.get(task["task_id"])
        assert state.status == "SUCCEEDED" and state.result
        if attempt == 0:
            assert state.report_status == "PENDING"
            async with service.repository.sessions.begin() as session:
                row = await session.get(RulePDFReport, task["task_id"])
                row.next_attempt_at = utcnow() - timedelta(seconds=1)
    response = await client.get(url(task))
    assert response.status_code == 503 and response.json()["code"] == "REPORT_GENERATION_FAILED"
    assert "private-font-path" not in response.text
    assert (await service.get(task["task_id"])).report_error.code == "REPORT_RENDER_FAILED"
    assert not await worker.run_once()
    assert await worker.repository.retry_failed(task["task_id"])
    assert await worker.run_once()
    assert (await service.get(task["task_id"])).report_status == "READY"
    assert not await worker.repository.retry_failed(task["task_id"])


async def test_expired_report_lease_is_recovered_and_stale_owner_is_fenced(report_api):
    _, service, _, reports = report_api
    task = await completed(report_api, generate=False)
    repository = reports.repository
    old = await repository.claim()
    async with service.repository.sessions.begin() as session:
        row = await session.get(RulePDFReport, task["task_id"])
        row.lease_until = utcnow() - timedelta(seconds=1)
    new = await repository.claim()
    assert new.claim_token != old.claim_token and new.attempts == 2
    assert not await repository.renew(old.task_id, old.claim_token)
    assert not await repository.complete(old.task_id, old.claim_token, "cipher", "a" * 64, 10)
    assert not await repository.fail(old.task_id, old.claim_token, "STALE")
    assert await repository.renew(new.task_id, new.claim_token)
    assert await repository.fail(new.task_id, new.claim_token, "TEST", permanent=True)


async def test_atomic_admission_and_legacy_reconciliation(report_api):
    _, service, _, reports = report_api
    task = await completed(report_api, generate=False)
    assert (await reports.repository.get(task["task_id"])).status == "PENDING"
    async with service.repository.sessions.begin() as session:
        await session.execute(delete(RulePDFReport).where(RulePDFReport.task_id == task["task_id"]))
    worker = PDFReportWorker(service)
    assert await worker.repository.reconcile() == 1
    assert await worker.repository.reconcile() == 0
    assert await worker.run_once()
    assert (await service.get(task["task_id"])).report_status == "READY"
    assert await worker.repository.reconcile() == 0


async def test_corrupt_download_and_invalid_source_never_return_pdf(report_api):
    client, service, _, _ = report_api
    task = await completed(report_api)
    async with service.repository.sessions.begin() as session:
        row = await session.get(RulePDFReport, task["task_id"])
        row.sha256 = "0" * 64
    assert (await client.get(url(task))).json()["code"] == "REPORT_DATA_UNAVAILABLE"
    task = await completed(report_api, generate=False)
    async with service.repository.sessions.begin() as session:
        row = await session.get(RuleValidationTask, task["task_id"])
        data = service.cipher().decrypt(row.result_ciphertext)
        data["rule_revision"] += 1
        row.result_ciphertext = service.cipher().encrypt(data)
    await PDFReportWorker(service).run_once()
    assert (await service.get(task["task_id"])).report_error.code == "REPORT_SOURCE_INVALID"


async def test_actual_size_guards_and_markup_are_safe(report_api):
    client, service, _, _ = report_api
    validation = task_fixtures.api_fixtures.payload()
    validation["form_data"] = validation["form_data"] | {
        "holder_name": '<img src="https://invalid.test/pixel"/> <b>中文</b>',
        "residence_address": "W" * 2000,
    }
    task = await completed(report_api, validation)
    _, text = extracted((await client.get(url(task))).content)
    assert '<img src="https://invalid.test/pixel"/>' in text
    for target in ["MAX_PAGES", "MAX_PDF_BYTES", "MAX_SNAPSHOT_BYTES"]:
        task = await completed(report_api, generate=False)
        with patch(f"backend.reports.renderer.{target}", 1):
            await PDFReportWorker(service).run_once()
        assert (await service.get(task["task_id"])).report_error.code == "REPORT_TOO_LARGE"


async def test_render_timeout_does_not_spawn_additional_threads(report_api):
    _, service, _, _ = report_api
    await completed(report_api, generate=False)
    worker = PDFReportWorker(service, RuleReportSettings(_env_file=None, timeout_seconds=0.1))
    started, release = threading.Event(), threading.Event()

    def blocked(data):
        started.set()
        release.wait(2)
        return b"%PDF-test"

    try:
        with patch("backend.workers.pdf_reports.render_report", blocked):
            await worker.run_once()
            assert started.is_set() and not worker._render.done()
            assert not await worker.run_once()
            release.set()
            await worker._render
    finally:
        release.set()


async def test_validation_result_and_report_admission_roll_back_together(report_api):
    client, service, _, reports = report_api
    submitted = await task_fixtures.submit(client)
    claim = await service.repository.claim()
    with patch("backend.repositories.pdf_reports.pending_report", side_effect=RuntimeError("admission failure")):
        with pytest.raises(RuntimeError):
            await service.repository.finish(claim.task_id, claim.claim_token, "cipher")
    saved = await service.repository.get(claim.task_id)
    assert saved.status == "RUNNING" and saved.result_ciphertext is None
    assert await reports.repository.get(claim.task_id) is None
    assert await service.repository.finish(claim.task_id, claim.claim_token, None, "TEST_FAILURE")


async def test_report_heartbeat_and_cpu_work_do_not_block_validation(report_api):
    client, service, validation_worker, _ = report_api
    first = await completed(report_api, generate=False)
    worker = PDFReportWorker(service, RuleReportSettings(_env_file=None, heartbeat_seconds=0.05))
    started, release = threading.Event(), threading.Event()
    from backend.reports.renderer import render_report

    def blocked(data):
        started.set()
        release.wait(2)
        return render_report(data)

    try:
        with patch("backend.workers.pdf_reports.render_report", blocked), patch.object(
            worker.repository, "renew", wraps=worker.repository.renew
        ) as renew:
            generation = asyncio.create_task(worker.run_once())
            assert await asyncio.to_thread(started.wait, 1)
            submitted = await task_fixtures.submit(client)
            assert await validation_worker.run_once()
            second = (await client.get(submitted.headers["Location"])).json()
            assert second["status"] == "SUCCEEDED" and second["report_status"] == "PENDING"
            await asyncio.sleep(0.08)
            assert renew.call_count >= 1
            release.set()
            await generation
    finally:
        release.set()
    assert (await service.get(first["task_id"])).report_status == "READY"


async def test_report_expiry_fences_generation_completion(report_api):
    _, service, _, reports = report_api
    task = await completed(report_api, generate=False)
    claim = await reports.repository.claim()
    async with service.repository.sessions.begin() as session:
        parent = await session.get(RuleValidationTask, task["task_id"])
        parent.expires_at = utcnow() - timedelta(seconds=1)
    assert not await reports.repository.complete(task["task_id"], claim.claim_token, "cipher", "a" * 64, 1)
    assert await reports.repository.cleanup() == 1
    assert (await reports.repository.get(task["task_id"])).error_code == "REPORT_EXPIRED"
    assert not await reports.repository.retry_failed(task["task_id"])


def test_pdf_cipher_domain_is_distinct_from_json_cipher():
    from backend.core.rule_tasks import TaskCipher
    cipher = TaskCipher([SecretStr(Fernet.generate_key().decode())])
    pdf = b"%PDF-test-sensitive"
    encrypted = cipher.encrypt_pdf(pdf)
    assert "sensitive" not in encrypted and cipher.decrypt_pdf(encrypted) == pdf
    with pytest.raises(ValueError):
        cipher.decrypt_pdf(cipher.encrypt({"value": "not a PDF"}))


async def test_worker_cli_once_connects_validation_and_report_loops(report_api):
    import os
    import sys

    client, service, _, _ = report_api
    submitted = await task_fixtures.submit(client)
    engine = service.repository.sessions.kw["bind"]
    environment = os.environ | {
        "DATABASE_URL": str(engine.url),
        "RULE_TASK_ENCRYPTION_KEYS": json.dumps([key.get_secret_value() for key in service.settings.encryption_keys]),
    }
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "backend.workers.rule_tasks", "--once", env=environment,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    _, errors = await process.communicate()
    assert process.returncode == 0, errors.decode()
    task = (await client.get(submitted.headers["Location"])).json()
    assert task["status"] == "SUCCEEDED" and task["report_status"] == "READY"
    assert (await client.get(task["report_url"])).content.startswith(b"%PDF-")
