"""Rule engine persistence model; matches the reviewed database schema."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class RuleSource(Base):
    __tablename__ = "rule_sources"
    __table_args__ = (
        CheckConstraint("length(jurisdiction_code) = 2"),
        {"schema": "crosstax"},
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    jurisdiction_code: Mapped[str] = mapped_column(String(2), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("TRUE"))
    etag: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_modified: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
