"""A portable transaction mutex for bounded queue admission."""

from sqlalchemy import CheckConstraint, Integer
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class RuleTaskQueueState(Base):
    __tablename__ = "rule_task_queue_state"
    __table_args__ = (CheckConstraint("id = 1", name="ck_rule_queue_singleton"), {"schema": "crosstax"})
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    generation: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
