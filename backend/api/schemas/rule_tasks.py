"""Two-step internal rule-validation contract, separate from business sessions."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict

from backend.api.schemas.presentation import TaskComparison
from backend.api.schemas.rule_engine import ValidationRequest, ValidationResponse


class TaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: UUID
    deadline_at: AwareDatetime | None = None
    validation: ValidationRequest


class TaskError(BaseModel):
    code: str
    message: str


class TaskResponse(BaseModel):
    task_id: UUID
    session_id: UUID
    status: Literal["PENDING", "RUNNING", "SUCCEEDED", "FAILED"]
    created_at: datetime
    deadline_at: datetime
    expires_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    rule_version_id: str
    rule_revision: int
    engine_build_id: str
    poll_after_ms: int
    comparison: TaskComparison | None = None
    report_status: Literal["PENDING", "RUNNING", "READY", "FAILED"] | None = None
    report_error: TaskError | None = None
    report_url: str | None = None
    result: ValidationResponse | None = None
    error: TaskError | None = None
