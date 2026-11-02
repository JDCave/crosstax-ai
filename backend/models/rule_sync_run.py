"""Rule engine persistence model; matches the reviewed database schema."""

from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class RuleSyncRun(Base):
    __tablename__ = "rule_sync_runs"
    __table_args__ = (
        CheckConstraint("trigger_type IN ('SCHEDULED', 'MANUAL')"),
        CheckConstraint("status IN ('RUNNING', 'SUCCEEDED', 'PARTIAL', 'FAILED')"),
        CheckConstraint(
            "(status = 'RUNNING' AND finished_at IS NULL)\n        OR (status <> 'RUNNING' AND finished_at IS NOT NULL)"
        ),
        CheckConstraint("finished_at IS NULL OR finished_at >= started_at"),
        Index("ix_rule_sync_runs_started", "started_at"),
        {"schema": "crosstax"},
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'RUNNING'"))
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
