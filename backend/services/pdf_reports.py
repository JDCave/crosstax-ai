"""Authorize through the main gateway; export only retained, completed task snapshots."""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from functools import lru_cache

from backend.api.schemas.rule_engine import ValidationRequest
from backend.core.rule_tasks import TaskCipher
from backend.infrastructure.exceptions import AppException
from backend.infrastructure.rule_tasks import aware, utcnow
from backend.reports.renderer import TEMPLATE_VERSION, ReportData, ReportTooLarge, render_report
from backend.services.rule_tasks import TaskService, get_task_service


@dataclass(frozen=True)
class PDFReport:
    content: bytes
    sha256: str
    filename: str
    template_version: str = TEMPLATE_VERSION


class PDFReportService:
    def __init__(self, tasks: TaskService, *, queue_timeout: float = 1, render_timeout: float = 15) -> None:
        self.tasks = tasks
        self.queue_timeout = queue_timeout
        self.render_timeout = render_timeout
        self._slots = asyncio.Semaphore(1)
        self._jobs: set[asyncio.Task[bytes]] = set()

    def _release(self, job: asyncio.Task[bytes]) -> None:
        self._jobs.discard(job)
        if not job.cancelled():
            job.exception()  # Consume exceptions even if the HTTP caller disconnected.
        self._slots.release()

    async def export(self, task_id: str) -> PDFReport:
        try:
            row = await self.tasks.repository.get(task_id)  # Session closes before rendering.
        except Exception as exc:
            raise AppException(503, "REPORT_DATA_UNAVAILABLE", "Report storage is unavailable") from exc
        if row is None:
            raise AppException(404, "TASK_NOT_FOUND", "Validation task does not exist")
        if aware(row.expires_at) <= utcnow():
            raise AppException(410, "TASK_EXPIRED", "Validation task content has expired")
        if row.status in ("PENDING", "RUNNING"):
            raise AppException(409, "REPORT_NOT_READY", "Validation task is not complete")
        if row.status != "SUCCEEDED":
            raise AppException(409, "REPORT_TASK_FAILED", "Failed tasks have no validation report")
        try:
            async with asyncio.timeout(self.queue_timeout):
                await self._slots.acquire()
        except TimeoutError as exc:
            raise AppException(503, "REPORT_BUSY", "Report generator is busy; retry later") from exc
        job: asyncio.Task[bytes] | None = None
        try:
            cipher = self.tasks.cipher()
            task = self.tasks.response(row, cipher)
            result = task.result
            if (
                result is None
                or result.execution is None
                or result.rule_version_id != row.rule_version_id
                or result.rule_revision != row.rule_revision
                or row.payload_ciphertext is None
            ):
                raise AppException(503, "REPORT_DATA_UNAVAILABLE", "Stored report data is incomplete or inconsistent")
            payload = cipher.decrypt(row.payload_ciphertext)
            validation = payload["validation"]
            ValidationRequest.model_validate_json(TaskCipher.canonical(validation))
            # Preserve the stored request, but verify its contract before presentation.
            frozen_policy = payload.get("form_policy")
            if result.execution.form_policy_id != (frozen_policy[1] if frozen_policy else None):
                raise AppException(503, "REPORT_DATA_UNAVAILABLE", "Stored report policy is inconsistent")
            job = asyncio.create_task(asyncio.to_thread(render_report, ReportData(task, validation)))
            self._jobs.add(job)
            job.add_done_callback(self._release)
            try:
                async with asyncio.timeout(self.render_timeout):
                    content = await asyncio.shield(job)
            except TimeoutError as exc:
                raise AppException(503, "REPORT_TIMEOUT", "Report generation timed out; retry later") from exc
            if aware(row.expires_at) <= utcnow():
                raise AppException(410, "TASK_EXPIRED", "Validation task content has expired")
            return PDFReport(content, hashlib.sha256(content).hexdigest(), f"crosstax-rule-report-{row.task_id}.pdf")
        except ReportTooLarge as exc:
            raise AppException(413, "REPORT_TOO_LARGE", "Report exceeds export limits") from exc
        except AppException:
            raise
        except Exception as exc:
            raise AppException(503, "REPORT_UNAVAILABLE", "Report could not be generated") from exc
        finally:
            if job is None:
                self._slots.release()


@lru_cache(maxsize=1)
def get_pdf_report_service() -> PDFReportService:
    return PDFReportService(get_task_service())
