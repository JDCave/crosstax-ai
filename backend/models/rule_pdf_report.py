"""Durable encrypted report artifact and independently leased generation state."""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class RulePDFReport(Base):
    __tablename__ = "rule_pdf_reports"
    __table_args__ = (
        CheckConstraint("status IN ('PENDING','RUNNING','READY','FAILED')", name="ck_pdf_report_status"),
        CheckConstraint("attempts >= 0", name="ck_pdf_report_attempts"),
        CheckConstraint("byte_length IS NULL OR byte_length > 0", name="ck_pdf_report_length"),
        Index("ix_pdf_report_claim", "status", "next_attempt_at", "lease_until"),
        {"schema": "crosstax"},
    )
    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("crosstax.rule_validation_tasks.task_id", ondelete="RESTRICT"), primary_key=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    template_version: Mapped[str] = mapped_column(String(64), nullable=False)
    render_build_id: Mapped[str] = mapped_column(String(64), nullable=False)
    content_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    byte_length: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    claim_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
