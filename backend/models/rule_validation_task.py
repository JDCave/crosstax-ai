"""Durable engine jobs; sensitive payloads are authenticated ciphertext only."""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class RuleValidationTask(Base):
    __tablename__ = "rule_validation_tasks"
    __table_args__ = (
        CheckConstraint("status IN ('PENDING','RUNNING','SUCCEEDED','FAILED')", name="ck_rule_task_status"),
        CheckConstraint("attempts >= 0", name="ck_rule_task_attempts"),
        Index("ix_rule_task_claim", "status", "lease_until", "created_at"),
        Index("ix_rule_task_expiry", "expires_at"),
        Index("ix_rule_task_session", "session_id", "created_at"),
        {"schema": "crosstax"},
    )
    task_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    rule_version_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("crosstax.rule_versions.version_id", ondelete="RESTRICT"), nullable=False
    )
    rule_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    engine_build_id: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    claim_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
