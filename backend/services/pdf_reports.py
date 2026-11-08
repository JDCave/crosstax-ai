"""Read a retained encrypted report artifact. Never render on the download path."""

import hashlib
from dataclasses import dataclass
from functools import lru_cache

from backend.infrastructure.exceptions import AppException
from backend.infrastructure.rule_tasks import aware, utcnow
from backend.repositories.pdf_reports import PDFReportRepository
from backend.services.rule_tasks import TaskService, get_task_service


@dataclass(frozen=True)
class PDFReport:
    content: bytes
    sha256: str
    filename: str
    template_version: str


class PDFReportService:
    def __init__(self, tasks: TaskService) -> None:
        self.tasks = tasks
        self.repository = PDFReportRepository(tasks.repository.sessions)

    async def export(self, task_id: str) -> PDFReport:
        try:
            row = await self.tasks.repository.get(task_id)
            if row is None:
                raise AppException(404, "TASK_NOT_FOUND", "Validation task does not exist")
            if aware(row.expires_at) <= utcnow():
                raise AppException(410, "TASK_EXPIRED", "Validation task content has expired")
            if row.status in ("PENDING", "RUNNING"):
                raise AppException(409, "REPORT_NOT_READY", "Validation task is not complete")
            if row.status != "SUCCEEDED":
                raise AppException(409, "REPORT_TASK_FAILED", "Failed tasks have no validation report")
            report = await self.repository.get(task_id, content=True)
            if report is None or report.status in ("PENDING", "RUNNING"):
                raise AppException(409, "REPORT_GENERATING", "报告生成中,请稍后重试")
            if report.status != "READY":
                raise AppException(503, "REPORT_GENERATION_FAILED", "报告生成失败,请联系服务方处理")
            if not report.content_ciphertext or not report.sha256 or not report.byte_length:
                raise AppException(503, "REPORT_DATA_UNAVAILABLE", "Stored report data is incomplete")
            content = self.tasks.cipher().decrypt_pdf(report.content_ciphertext)
            digest = hashlib.sha256(content).hexdigest()
            if not content.startswith(b"%PDF-") or digest != report.sha256 or len(content) != report.byte_length:
                raise AppException(503, "REPORT_DATA_UNAVAILABLE", "Stored report integrity check failed")
            if aware(row.expires_at) <= utcnow():
                raise AppException(410, "TASK_EXPIRED", "Validation task content has expired")
            return PDFReport(content, digest, f"crosstax-rule-report-{task_id}.pdf", report.template_version)
        except AppException:
            raise
        except Exception as exc:
            raise AppException(503, "REPORT_UNAVAILABLE", "Report could not be read") from exc


@lru_cache(maxsize=1)
def get_pdf_report_service() -> PDFReportService:
    return PDFReportService(get_task_service())
