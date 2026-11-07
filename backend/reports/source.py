"""Validate stored source consistency without re-running rules or AI."""

from backend.api.schemas.rule_engine import ValidationRequest
from backend.core.rule_tasks import TaskCipher
from backend.models import RuleValidationTask
from backend.reports.renderer import ReportData
from backend.services.rule_tasks import TaskService


def load_report_data(tasks: TaskService, row: RuleValidationTask) -> ReportData:
    cipher = tasks.cipher()
    task = tasks.response(row, cipher)
    result = task.result
    if (
        result is None
        or result.execution is None
        or result.rule_version_id != row.rule_version_id
        or result.rule_revision != row.rule_revision
        or row.payload_ciphertext is None
    ):
        raise ValueError("Stored report data is inconsistent")
    payload = cipher.decrypt(row.payload_ciphertext)
    validation = payload["validation"]
    ValidationRequest.model_validate_json(TaskCipher.canonical(validation))
    frozen_policy = payload.get("form_policy")
    if result.execution.form_policy_id != (frozen_policy[1] if frozen_policy else None):
        raise ValueError("Stored form policy is inconsistent")
    return ReportData(task, validation)
