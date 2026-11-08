"""Rule engine persistence model; matches the reviewed database schema."""

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class RuleEngineState(Base):
    __tablename__ = "rule_engine_state"
    __table_args__ = (
        CheckConstraint("id = 1"),
        CheckConstraint("revision >= 0"),
        CheckConstraint(
            "(active_version_id IS NULL AND activated_at IS NULL) "
            "OR (active_version_id IS NOT NULL AND activated_at IS NOT NULL)"
        ),
        {"schema": "crosstax"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, nullable=False)
    active_version_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("crosstax.rule_versions.version_id", ondelete="RESTRICT"), nullable=True
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
