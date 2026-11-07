"""Short ORM transactions for admission, leases and fenced terminal commits."""

from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import uuid4

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql.elements import ColumnElement

from backend.core.rule_tasks import RuleTaskSettings
from backend.infrastructure.exceptions import AppException
from backend.models import RuleTaskQueueState, RuleValidationTask


def utcnow() -> datetime:
    return datetime.now(UTC)


def aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


ACTIVE = ("PENDING", "RUNNING")


class TaskRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], settings: RuleTaskSettings) -> None:
        self.sessions = sessions
        self.settings = settings

    async def get(self, task_id: str) -> RuleValidationTask | None:
        async with self.sessions() as session:
            return await session.get(RuleValidationTask, task_id)

    async def by_key(self, key: str) -> RuleValidationTask | None:
        async with self.sessions() as session:
            return cast(
                RuleValidationTask | None,
                await session.scalar(select(RuleValidationTask).where(RuleValidationTask.idempotency_key == key)),
            )

    async def enqueue(self, task: RuleValidationTask) -> RuleValidationTask:
        # The singleton write serializes capacity checking on both SQLite and PostgreSQL.
        for attempt in range(3):
            try:
                async with self.sessions() as session, session.begin():
                    state = await session.get(RuleTaskQueueState, 1)
                    if state is None:
                        session.add(RuleTaskQueueState(id=1, generation=0))
                        await session.flush()
                    await session.execute(
                        update(RuleTaskQueueState)
                        .where(RuleTaskQueueState.id == 1)
                        .values(generation=RuleTaskQueueState.generation + 1)
                    )
                    existing = await session.scalar(
                        select(RuleValidationTask).where(RuleValidationTask.idempotency_key == task.idempotency_key)
                    )
                    if existing:
                        return existing
                    now = utcnow()
                    count = await session.scalar(
                        select(func.count())
                        .select_from(RuleValidationTask)
                        .where(
                            RuleValidationTask.status.in_(ACTIVE),
                            RuleValidationTask.deadline_at > now,
                            RuleValidationTask.expires_at > now,
                        )
                    )
                    if (count or 0) >= self.settings.capacity:
                        raise AppException(503, "TASK_QUEUE_FULL", "Validation queue is full; retry later")
                    session.add(task)
                    await session.flush()
                return task
            except IntegrityError:
                existing = await self.by_key(task.idempotency_key)
                if existing:
                    return existing
                if attempt == 2:
                    raise
        raise RuntimeError("Unreachable admission state")

    async def cleanup(self) -> int:
        now = utcnow()
        async with self.sessions() as session, session.begin():
            rows = await session.scalars(
                select(RuleValidationTask)
                .where(
                    RuleValidationTask.expires_at <= now,
                    or_(
                        RuleValidationTask.payload_ciphertext.is_not(None),
                        RuleValidationTask.result_ciphertext.is_not(None),
                    ),
                )
                .limit(100)
            )
            count = 0
            for task in rows:
                task.payload_ciphertext = None
                task.result_ciphertext = None
                task.claim_token = None
                task.lease_until = None
                if task.status in ACTIVE:
                    task.status = "FAILED"
                    task.error_code = "TASK_EXPIRED"
                    task.completed_at = now
                count += 1
            return count

    async def claim(self) -> RuleValidationTask | None:
        now = utcnow()
        available = or_(
            RuleValidationTask.status == "PENDING",
            and_(
                RuleValidationTask.status == "RUNNING",
                RuleValidationTask.lease_until <= now,
            ),
        )
        async with self.sessions() as session, session.begin():
            # Expiry is a terminal state only when no valid lease can still own execution.
            await session.execute(
                update(RuleValidationTask)
                .where(
                    available,
                    or_(
                        RuleValidationTask.deadline_at <= now, RuleValidationTask.attempts >= self.settings.max_attempts
                    ),
                )
                .values(
                    status="FAILED",
                    error_code="TASK_DEADLINE_OR_ATTEMPTS_EXCEEDED",
                    completed_at=now,
                    claim_token=None,
                    lease_until=None,
                )
            )
            task = await session.scalar(
                select(RuleValidationTask)
                .where(
                    available,
                    RuleValidationTask.deadline_at > now,
                    RuleValidationTask.expires_at > now,
                    RuleValidationTask.attempts < self.settings.max_attempts,
                )
                .order_by(RuleValidationTask.created_at, RuleValidationTask.task_id)
                .limit(1)
            )
            if task is None:
                return None
            token = str(uuid4())
            claimed = await session.scalar(
                update(RuleValidationTask)
                .where(
                    RuleValidationTask.task_id == task.task_id,
                    available,
                    RuleValidationTask.attempts == task.attempts,
                )
                .values(
                    status="RUNNING",
                    claim_token=token,
                    attempts=RuleValidationTask.attempts + 1,
                    started_at=now,
                    lease_until=min(now + timedelta(seconds=self.settings.lease_seconds), aware(task.deadline_at)),
                )
                .returning(RuleValidationTask.task_id)
                .execution_options(synchronize_session=False)
            )
            if claimed is None:
                return None
            await session.refresh(task)
            return task

    async def renew(self, task_id: str, token: str) -> bool:
        now = utcnow()
        async with self.sessions() as session, session.begin():
            deadline = await session.scalar(
                select(RuleValidationTask.deadline_at).where(
                    *self._ownership(task_id, token, now),
                    RuleValidationTask.deadline_at > now,
                )
            )
            if deadline is None:
                return False
            value = await session.scalar(
                update(RuleValidationTask)
                .where(
                    *self._ownership(task_id, token, now),
                    RuleValidationTask.deadline_at > now,
                )
                .values(lease_until=min(now + timedelta(seconds=self.settings.lease_seconds), aware(deadline)))
                .returning(RuleValidationTask.task_id)
            )
            return value is not None

    @staticmethod
    def _ownership(task_id: str, token: str, now: datetime) -> list[ColumnElement[bool]]:
        return [
            RuleValidationTask.task_id == task_id,
            RuleValidationTask.status == "RUNNING",
            RuleValidationTask.claim_token == token,
            RuleValidationTask.lease_until > now,
        ]

    async def finish(self, task_id: str, token: str, ciphertext: str | None, error: str | None = None) -> bool:
        now = utcnow()
        async with self.sessions() as session, session.begin():
            filters = self._ownership(task_id, token, now)
            if error is None:
                filters.append(RuleValidationTask.deadline_at > now)
            value = await session.scalar(
                update(RuleValidationTask)
                .where(*filters)
                .values(
                    status="FAILED" if error else "SUCCEEDED",
                    result_ciphertext=ciphertext,
                    error_code=error,
                    completed_at=now,
                    claim_token=None,
                    lease_until=None,
                )
                .returning(RuleValidationTask.task_id)
            )
            return value is not None
