"""Append-only rule activation history."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class RulePublication(Base):
    __tablename__ = "rule_publications"
    __table_args__ = ({"schema": "crosstax"},)
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    version_id: Mapped[str] = mapped_column(String(64), ForeignKey("crosstax.rule_versions.version_id"), nullable=False)
    previous_version_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("crosstax.rule_versions.version_id"))
    actor: Mapped[str] = mapped_column(String(200), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
