"""Rule engine persistence model; matches the reviewed database schema."""

from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class RuleVersion(Base):
    __tablename__ = "rule_versions"
    __table_args__ = (
        CheckConstraint("length(version_id) = 64"),
        CheckConstraint("schema_version > 0"),
        CheckConstraint("status IN ('CANDIDATE', 'APPROVED', 'REJECTED')"),
        CheckConstraint(
            "(status = 'APPROVED' AND approved_at IS NOT NULL) OR (status <> 'APPROVED' AND approved_at IS NULL)"
        ),
        Index("ix_rule_versions_status_created", "status", "created_at"),
        {"schema": "crosstax"},
    )

    version_id: Mapped[str] = mapped_column(String(64), primary_key=True, nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    rules: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'CANDIDATE'"))
    validation_report: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    extraction_metadata: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
