"""Rule engine persistence model; matches the reviewed database schema."""

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class RuleDocument(Base):
    __tablename__ = "rule_documents"
    __table_args__ = (
        CheckConstraint("length(content_hash) = 64"),
        UniqueConstraint("source_id", "content_hash"),
        Index("ix_rule_documents_sync_run", "sync_run_id"),
        Index("ix_rule_documents_source_fetched", "source_id", "fetched_at"),
        {"schema": "crosstax"},
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, nullable=False)
    source_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("crosstax.rule_sources.id", ondelete="RESTRICT"), nullable=False
    )
    sync_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("crosstax.rule_sync_runs.id", ondelete="RESTRICT"), nullable=False
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    raw_content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
