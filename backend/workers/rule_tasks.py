"""Independent durable validation worker: uv run python -m backend.workers.rule_tasks."""

import argparse
import asyncio
import logging
from contextlib import suppress
from typing import Any
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError

from backend.api.schemas.rule_engine import ValidationRequest
from backend.core.rule_tasks import RuleTaskSettings, TaskCipher
from backend.engine.regulatory_parameters import FormPolicy
from backend.engine.reproducibility import canonical_hash
from backend.engine.rule_loader import RuleLoader, compile_snapshot
from backend.engine.structured_contracts import FormData
from backend.engine.validation import ValidationEngine
from backend.infrastructure.rule_tasks import aware, utcnow
from backend.services.rule_api import RuleAPIService
from backend.services.rule_tasks import TaskService, task_build_id


class RuleTaskWorker:
    def __init__(self, service: TaskService) -> None:
        self.service = service

    async def _heartbeat(self, task_id: str, token: str, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                await asyncio.wait_for(stop.wait(), self.service.settings.heartbeat_seconds)
                return
            except TimeoutError:
                pass
            if not await self.service.repository.renew(task_id, token):
                return

    async def run_once(self) -> bool:
        cipher = self.service.cipher()  # Fail startup/iteration before claiming without a valid key.
        repository = self.service.repository
        await repository.cleanup()
        task = await repository.claim()
        if task is None:
            return False
        token = task.claim_token
        assert token is not None
        stop = asyncio.Event()
        computation: asyncio.Task[Any] | None = None
        heartbeat: asyncio.Task[None] | None = None
        try:
            remaining = (aware(task.deadline_at) - utcnow()).total_seconds()
            async with asyncio.timeout(max(0, remaining)):
                if task.engine_build_id != task_build_id():
                    await repository.finish(task.task_id, token, None, "TASK_BUILD_MISMATCH")
                    return True
                payload = cipher.decrypt(task.payload_ciphertext or "")
                request = ValidationRequest.model_validate_json(TaskCipher.canonical(payload["validation"]))
                snapshot = compile_snapshot(task.rule_version_id, task.rule_revision, payload["rules"])
                policy = payload["form_policy"]
                if isinstance(request.form_data, FormData) and policy is None:
                    raise ValueError("Structured tasks require a frozen form policy")
                if policy is not None:
                    config = FormPolicy.model_validate(policy[0]).model_dump(mode="json")
                    if canonical_hash(config) != policy[1]:
                        raise ValueError("Invalid frozen form policy")
                    policy = (config, policy[1])
                computation = asyncio.create_task(
                    self.service.api.validate_frozen(
                        request.form_data,
                        request.policy,
                        request.indicia_issues,
                        request.include_guidance,
                        snapshot,
                        policy,
                        offload=True,
                    )
                )
                heartbeat = asyncio.create_task(self._heartbeat(task.task_id, token, stop))
                done, _ = await asyncio.wait((computation, heartbeat), return_when=asyncio.FIRST_COMPLETED)
                if heartbeat in done:
                    # Includes database/lease failure. Never commit using uncertain ownership.
                    with suppress(Exception):
                        heartbeat.result()
                    return True
                result = computation.result()
                await repository.finish(task.task_id, token, cipher.encrypt(result.model_dump(mode="json")))
        except TimeoutError:
            # Lease ends at the deadline; a later claim scan terminalizes the expired task.
            await repository.finish(task.task_id, token, None, "TASK_DEADLINE_EXCEEDED")
        except Exception:
            # Never persist exception strings, SQL parameters, form values or provider response bodies.
            await repository.finish(task.task_id, token, None, "TASK_EXECUTION_FAILED")
        finally:
            stop.set()
            if computation is not None:
                computation.cancel()
            # Let an in-flight short heartbeat transaction close before releasing its connection.
            await asyncio.gather(*(t for t in (computation, heartbeat) if t is not None), return_exceptions=True)
        return True


async def run(cleanup_only: bool = False, once: bool = False, retry_report: str | None = None) -> None:
    from backend.infrastructure.database import create_worker_database

    engine, sessions = create_worker_database()
    try:
        service = TaskService(RuleAPIService(ValidationEngine(RuleLoader(sessions))), RuleTaskSettings())
        service.cipher()
        from backend.workers.pdf_reports import PDFReportWorker

        worker = RuleTaskWorker(service)
        reports = PDFReportWorker(service)
        if retry_report:
            if not await reports.repository.retry_failed(retry_report):
                raise ValueError("Only retained failed reports can be retried")
            return
        if cleanup_only:
            while await service.repository.cleanup():
                pass
            while await reports.repository.cleanup():
                pass
            return
        if once:
            await worker.run_once()
            await reports.run_once()
            return

        async def loop(report_loop: bool) -> None:
            while True:
                try:
                    worked = await reports.run_once() if report_loop else await worker.run_once()
                except SQLAlchemyError:
                    logging.getLogger(__name__).warning("Task storage unavailable; worker will retry")
                    await asyncio.sleep(1)
                    continue
                if not worked:
                    await asyncio.sleep(0.25)

        async with asyncio.TaskGroup() as group:
            group.create_task(loop(False))
            group.create_task(loop(True))
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the encrypted rule-validation worker")
    parser.add_argument("--once", action="store_true", help="Try one validation and one report task, then exit")
    parser.add_argument("--cleanup", action="store_true", help="Purge all expired ciphertext batches and exit")
    parser.add_argument(
        "--retry-report", type=UUID, help="Requeue a retained failed report without rerunning validation"
    )
    args = parser.parse_args()
    try:
        asyncio.run(
            run(
                cleanup_only=args.cleanup,
                once=args.once,
                retry_report=str(args.retry_report) if args.retry_report else None,
            )
        )
    except KeyboardInterrupt:
        pass
    except Exception:
        raise SystemExit("Rule task worker stopped; check database and encryption configuration") from None


if __name__ == "__main__":
    main()
