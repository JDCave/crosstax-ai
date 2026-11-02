"""Engine-owned audit envelope; does not replace the main AuditSession."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class RuleAuditRecord(Base):
    __tablename__ = "rule_audit_records"
    __table_args__ = ({"schema": "crosstax"},)
    session_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    rule_version_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("crosstax.rule_versions.version_id"), nullable=False
    )
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    form_data: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    upstream_issues: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)
    result: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
