"""Portable short transactions for recoverable report generation and artifact storage."""

from datetime import datetime, timedelta
from typing import cast
from uuid import uuid4

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import defer
from sqlalchemy.sql.elements import ColumnElement

from backend.core.rule_reports import RuleReportSettings, get_report_settings
from backend.infrastructure.rule_tasks import aware, utcnow
from backend.models import RulePDFReport, RuleValidationTask
from backend.reports.renderer import TEMPLATE_VERSION, report_build_id


def pending_report(task_id: str, now: datetime) -> RulePDFReport:
    return RulePDFReport(
        task_id=task_id,
        status="PENDING",
        template_version=TEMPLATE_VERSION,
        render_build_id=report_build_id(),
        attempts=0,
        created_at=now,
        next_attempt_at=now,
    )


class PDFReportRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], settings: RuleReportSettings | None = None) -> None:
        self.sessions = sessions
        self.settings = settings or get_report_settings()

    async def get(self, task_id: str, *, content: bool = False) -> RulePDFReport | None:
        statement = select(RulePDFReport).where(RulePDFReport.task_id == task_id)
        if not content:
            statement = statement.options(defer(RulePDFReport.content_ciphertext))
        async with self.sessions() as session:
            return cast(RulePDFReport | None, await session.scalar(statement))

    async def reconcile(self) -> int:
        async with self.sessions() as session, session.begin():
            ids = await session.scalars(
                select(RuleValidationTask.task_id)
                .where(
                    RuleValidationTask.status == "SUCCEEDED",
                    RuleValidationTask.expires_at > utcnow(),
                    RuleValidationTask.payload_ciphertext.is_not(None),
                    RuleValidationTask.result_ciphertext.is_not(None),
                    ~select(RulePDFReport.task_id).where(RulePDFReport.task_id == RuleValidationTask.task_id).exists(),
                )
                .order_by(RuleValidationTask.created_at)
                .limit(100)
            )
            values = list(ids)
            session.add_all([pending_report(task_id, utcnow()) for task_id in values])
            return len(values)

    @staticmethod
    def live_parent(now: datetime) -> ColumnElement[bool]:
        return (
            select(RuleValidationTask.task_id)
            .where(
                RuleValidationTask.task_id == RulePDFReport.task_id,
                RuleValidationTask.status == "SUCCEEDED",
                RuleValidationTask.expires_at > now,
            )
            .exists()
        )

    @staticmethod
    def ownership(task_id: str, token: str, now: datetime) -> list[ColumnElement[bool]]:
        return [
            RulePDFReport.task_id == task_id,
            RulePDFReport.status == "RUNNING",
            RulePDFReport.claim_token == token,
            RulePDFReport.lease_until > now,
            PDFReportRepository.live_parent(now),
        ]

    async def claim(self) -> RulePDFReport | None:
        now = utcnow()
        available = or_(
            and_(RulePDFReport.status == "PENDING", RulePDFReport.next_attempt_at <= now),
            and_(RulePDFReport.status == "RUNNING", RulePDFReport.lease_until <= now),
        )
        async with self.sessions() as session, session.begin():
            await session.execute(
                update(RulePDFReport)
                .where(
                    available,
                    RulePDFReport.attempts >= self.settings.max_attempts,
                )
                .values(
                    status="FAILED",
                    error_code="REPORT_ATTEMPTS_EXCEEDED",
                    completed_at=now,
                    claim_token=None,
                    lease_until=None,
                )
            )
            row = await session.scalar(
                select(RulePDFReport)
                .where(
                    available,
                    self.live_parent(now),
                    RulePDFReport.attempts < self.settings.max_attempts,
                )
                .order_by(RulePDFReport.created_at, RulePDFReport.task_id)
                .limit(1)
            )
            if row is None:
                return None
            expires = await session.scalar(
                select(RuleValidationTask.expires_at).where(RuleValidationTask.task_id == row.task_id)
            )
            assert expires is not None
            token = str(uuid4())
            claimed = await session.scalar(
                update(RulePDFReport)
                .where(
                    RulePDFReport.task_id == row.task_id,
                    available,
                    RulePDFReport.attempts == row.attempts,
                )
                .values(
                    status="RUNNING",
                    attempts=RulePDFReport.attempts + 1,
                    claim_token=token,
                    started_at=now,
                    error_code=None,
                    lease_until=min(now + timedelta(seconds=self.settings.lease_seconds), aware(expires)),
                )
                .returning(RulePDFReport.task_id)
                .execution_options(synchronize_session=False)
            )
            if claimed is None:
                return None
            await session.refresh(row)
            return row

    async def renew(self, task_id: str, token: str) -> bool:
        now = utcnow()
        async with self.sessions() as session, session.begin():
            expires = await session.scalar(
                select(RuleValidationTask.expires_at).where(
                    RuleValidationTask.task_id == task_id, RuleValidationTask.expires_at > now
                )
            )
            if expires is None:
                return False
            value = await session.scalar(
                update(RulePDFReport)
                .where(*self.ownership(task_id, token, now))
                .values(lease_until=min(now + timedelta(seconds=self.settings.lease_seconds), aware(expires)))
                .returning(RulePDFReport.task_id)
            )
            return value is not None

    async def complete(self, task_id: str, token: str, ciphertext: str, sha256: str, length: int) -> bool:
        now = utcnow()
        async with self.sessions() as session, session.begin():
            value = await session.scalar(
                update(RulePDFReport)
                .where(*self.ownership(task_id, token, now))
                .values(
                    status="READY",
                    content_ciphertext=ciphertext,
                    sha256=sha256,
                    byte_length=length,
                    completed_at=now,
                    error_code=None,
                    claim_token=None,
                    lease_until=None,
                )
                .returning(RulePDFReport.task_id)
            )
            return value is not None

    async def fail(self, task_id: str, token: str, error: str, *, permanent: bool = False) -> bool:
        now = utcnow()
        async with self.sessions() as session, session.begin():
            attempts = await session.scalar(select(RulePDFReport.attempts).where(*self.ownership(task_id, token, now)))
            if attempts is None:
                return False
            terminal = permanent or attempts >= self.settings.max_attempts
            value = await session.scalar(
                update(RulePDFReport)
                .where(*self.ownership(task_id, token, now))
                .values(
                    status="FAILED" if terminal else "PENDING",
                    error_code=error,
                    completed_at=now if terminal else None,
                    claim_token=None,
                    lease_until=None,
                    next_attempt_at=now + timedelta(seconds=min(2**attempts, 60)),
                )
                .returning(RulePDFReport.task_id)
            )
            return value is not None

    async def cleanup(self) -> int:
        now = utcnow()
        async with self.sessions() as session, session.begin():
            ids = list(
                await session.scalars(
                    select(RulePDFReport.task_id)
                    .join(
                        RuleValidationTask,
                        RuleValidationTask.task_id == RulePDFReport.task_id,
                    )
                    .where(
                        RuleValidationTask.expires_at <= now,
                        or_(
                            RulePDFReport.content_ciphertext.is_not(None),
                            RulePDFReport.status.in_(("PENDING", "RUNNING")),
                        ),
                    )
                    .limit(100)
                )
            )
            if ids:
                await session.execute(
                    update(RulePDFReport)
                    .where(RulePDFReport.task_id.in_(ids))
                    .values(
                        content_ciphertext=None,
                        status="FAILED",
                        error_code="REPORT_EXPIRED",
                        completed_at=now,
                        claim_token=None,
                        lease_until=None,
                    )
                )
            return len(ids)

    async def retry_failed(self, task_id: str) -> bool:
        now = utcnow()
        async with self.sessions() as session, session.begin():
            value = await session.scalar(
                update(RulePDFReport)
                .where(
                    RulePDFReport.task_id == task_id,
                    RulePDFReport.status == "FAILED",
                    self.live_parent(now),
                )
                .values(
                    status="PENDING",
                    attempts=0,
                    error_code=None,
                    completed_at=None,
                    claim_token=None,
                    lease_until=None,
                    next_attempt_at=now,
                    content_ciphertext=None,
                    sha256=None,
                    byte_length=None,
                    template_version=TEMPLATE_VERSION,
                    render_build_id=report_build_id(),
                )
                .returning(RulePDFReport.task_id)
            )
            return value is not None
