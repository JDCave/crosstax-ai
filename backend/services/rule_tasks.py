"""Task submission/query orchestration; no rule computation in request handlers."""

import hashlib
import hmac
from datetime import timedelta
from functools import lru_cache
from pathlib import Path
from typing import Literal, cast
from uuid import uuid4

from backend.api.schemas.rule_engine import ValidationResponse
from backend.api.schemas.rule_tasks import TaskError, TaskRequest, TaskResponse
from backend.core.rule_tasks import RuleTaskSettings, TaskCipher
from backend.engine.reproducibility import engine_build_id
from backend.engine.structured_contracts import FormData
from backend.engine.structured_validation import load_form_policy
from backend.infrastructure.exceptions import AppException, NotFoundException
from backend.infrastructure.rule_tasks import TaskRepository, aware, utcnow
from backend.models import RuleValidationTask, RuleVersion
from backend.services.rule_api import RuleAPIService, get_rule_api_service


@lru_cache(maxsize=1)
def task_build_id() -> str:
    """Pin the engine plus its task adapter/AI implementation and request contracts."""
    root = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256(engine_build_id().encode())
    for directory in ("services", "agents", "api/schemas", "core"):
        for path in sorted((root / directory).glob("*.py")):
            digest.update(str(path.relative_to(root)).encode())
            digest.update(path.read_bytes())
    digest.update((root / "workers/rule_tasks.py").read_bytes())
    return digest.hexdigest()


class TaskService:
    def __init__(self, api: RuleAPIService, settings: RuleTaskSettings) -> None:
        self.api = api
        self.settings = settings
        self.repository = TaskRepository(api.engine.loader.sessions, settings)

    def cipher(self) -> TaskCipher:
        try:
            return TaskCipher(self.settings.encryption_keys)
        except (ValueError, UnicodeError) as exc:
            raise AppException(503, "TASK_ENCRYPTION_UNAVAILABLE", "Task encryption must be configured") from exc

    @staticmethod
    def _same_request(row: RuleValidationTask, digests: list[str]) -> None:
        if not any(hmac.compare_digest(row.request_digest, value) for value in digests):
            raise AppException(409, "IDEMPOTENCY_CONFLICT", "Idempotency key belongs to a different request")

    async def submit(self, request: TaskRequest, key: str) -> TaskResponse:
        cipher = self.cipher()
        identity = request.model_dump(mode="json")
        digests = cipher.digests(identity)
        existing = await self.repository.by_key(key)
        if existing:
            self._same_request(existing, digests)
            return self.response(existing, cipher)
        now = utcnow()
        deadline = min(
            request.deadline_at or now + timedelta(seconds=self.settings.timeout_seconds),
            now + timedelta(seconds=self.settings.timeout_seconds),
        )
        if deadline <= now:
            raise AppException(422, "TASK_DEADLINE_INVALID", "Task deadline must be in the future")
        try:
            snapshot = await self.api.engine.loader.refresh()
        except NotFoundException as exc:
            raise AppException(503, "NO_ACTIVE_RULES", "No active rule version is available") from exc
        async with self.repository.sessions() as session:
            version = await session.get(RuleVersion, snapshot.version_id)
            if version is None or version.status != "APPROVED":
                raise AppException(503, "NO_ACTIVE_RULES", "No approved rule version is available")
            rules = version.rules
        policy = load_form_policy() if isinstance(request.validation.form_data, FormData) else None
        task = RuleValidationTask(
            task_id=str(uuid4()),
            session_id=str(request.session_id),
            idempotency_key=key,
            request_digest=digests[0],
            status="PENDING",
            rule_version_id=snapshot.version_id,
            rule_revision=snapshot.revision,
            engine_build_id=task_build_id(),
            attempts=0,
            payload_ciphertext=cipher.encrypt(
                {
                    "validation": request.validation.model_dump(mode="json", exclude_none=True),
                    "rules": rules,
                    "form_policy": policy,
                }
            ),
            created_at=now,
            deadline_at=deadline,
            expires_at=now + timedelta(seconds=self.settings.retention_seconds),
        )
        saved = await self.repository.enqueue(task)
        self._same_request(saved, digests)
        return self.response(saved, cipher)

    async def get(self, task_id: str) -> TaskResponse:
        row = await self.repository.get(task_id)
        if row is None:
            raise AppException(404, "TASK_NOT_FOUND", "Validation task does not exist")
        # Expiry remains observable even if encryption keys have been removed after retention.
        if aware(row.expires_at) <= utcnow():
            raise AppException(410, "TASK_EXPIRED", "Validation task content has expired")
        return self.response(row, self.cipher())

    @staticmethod
    def response(row: RuleValidationTask, cipher: TaskCipher) -> TaskResponse:
        if aware(row.expires_at) <= utcnow():
            raise AppException(410, "TASK_EXPIRED", "Validation task content has expired")
        result = (
            ValidationResponse.model_validate(cipher.decrypt(row.result_ciphertext))
            if row.status == "SUCCEEDED" and row.result_ciphertext
            else None
        )
        error = (
            TaskError(code=row.error_code, message="Validation execution could not complete; submit a new task")
            if row.error_code
            else None
        )
        return TaskResponse(
            task_id=row.task_id,
            session_id=row.session_id,
            status=cast("Literal['PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED']", row.status),
            created_at=aware(row.created_at),
            deadline_at=aware(row.deadline_at),
            expires_at=aware(row.expires_at),
            started_at=aware(row.started_at) if row.started_at else None,
            completed_at=aware(row.completed_at) if row.completed_at else None,
            rule_version_id=row.rule_version_id,
            rule_revision=row.rule_revision,
            engine_build_id=row.engine_build_id,
            poll_after_ms=500 if row.status in ("PENDING", "RUNNING") else 0,
            result=result,
            error=error,
        )


@lru_cache(maxsize=1)
def get_task_service() -> TaskService:
    return TaskService(get_rule_api_service(), RuleTaskSettings())
