"""Rule engine persistence model; matches the reviewed database schema."""

from sqlalchemy import ForeignKey, Index, PrimaryKeyConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class RuleVersionDocument(Base):
    __tablename__ = "rule_version_documents"
    __table_args__ = (
        PrimaryKeyConstraint("version_id", "document_id"),
        Index("ix_rule_version_documents_document", "document_id"),
        {"schema": "crosstax"},
    )

    version_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("crosstax.rule_versions.version_id", ondelete="RESTRICT"), nullable=False
    )
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("crosstax.rule_documents.id", ondelete="RESTRICT"), nullable=False
    )
