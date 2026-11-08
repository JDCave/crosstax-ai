"""Independent report loop sharing the validation worker's one-connection pool."""

import asyncio
import hashlib
from contextlib import suppress

from backend.core.rule_reports import RuleReportSettings
from backend.infrastructure.rule_tasks import aware, utcnow
from backend.reports.renderer import ReportTooLarge, render_report, report_build_id
from backend.reports.source import load_report_data
from backend.repositories.pdf_reports import PDFReportRepository
from backend.services.rule_tasks import TaskService


class PDFReportWorker:
    def __init__(self, tasks: TaskService, settings: RuleReportSettings | None = None) -> None:
        self.tasks = tasks
        self.repository = PDFReportRepository(tasks.repository.sessions, settings)
        self._render: asyncio.Task[bytes] | None = None

    async def _heartbeat(self, task_id: str, token: str, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                await asyncio.wait_for(stop.wait(), self.repository.settings.heartbeat_seconds)
                return
            except TimeoutError:
                pass
            if not await self.repository.renew(task_id, token):
                return

    @staticmethod
    def _consume(job: asyncio.Task[bytes]) -> None:
        if not job.cancelled():
            job.exception()

    async def run_once(self) -> bool:
        if self._render is not None and not self._render.done():
            return False  # Cancellation/timeouts never release a still-running CPU thread's capacity.
        self.tasks.cipher()
        await self.repository.cleanup()
        await self.repository.reconcile()
        report = await self.repository.claim()
        if report is None:
            return False
        token = report.claim_token
        assert token is not None
        stop = asyncio.Event()
        heartbeat: asyncio.Task[None] | None = None
        try:
            if report.render_build_id != report_build_id():
                await self.repository.fail(report.task_id, token, "REPORT_BUILD_MISMATCH", permanent=True)
                return True
            row = await self.tasks.repository.get(report.task_id)
            if row is None:
                raise ValueError("Parent task is unavailable")
            budget = min(self.repository.settings.timeout_seconds, (aware(row.expires_at) - utcnow()).total_seconds())
            async with asyncio.timeout(max(0, budget)):
                data = load_report_data(self.tasks, row)
                self._render = asyncio.create_task(asyncio.to_thread(render_report, data))
                self._render.add_done_callback(self._consume)
                heartbeat = asyncio.create_task(self._heartbeat(report.task_id, token, stop))
                done, _ = await asyncio.wait((self._render, heartbeat), return_when=asyncio.FIRST_COMPLETED)
                if heartbeat in done:
                    with suppress(Exception):
                        heartbeat.result()
                    return True
                content = self._render.result()
                await self.repository.complete(
                    report.task_id,
                    token,
                    self.tasks.cipher().encrypt_pdf(content),
                    hashlib.sha256(content).hexdigest(),
                    len(content),
                )
        except ReportTooLarge:
            await self.repository.fail(report.task_id, token, "REPORT_TOO_LARGE", permanent=True)
        except ValueError:
            await self.repository.fail(report.task_id, token, "REPORT_SOURCE_INVALID", permanent=True)
        except TimeoutError:
            await self.repository.fail(report.task_id, token, "REPORT_TIMEOUT")
        except Exception:
            await self.repository.fail(report.task_id, token, "REPORT_RENDER_FAILED")
        finally:
            stop.set()
            if heartbeat is not None:
                await asyncio.gather(heartbeat, return_exceptions=True)
        return True
