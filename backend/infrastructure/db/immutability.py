"""ORM guardrails; database administrators remain outside this trust boundary."""

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from backend.models.rule_audit_record import RuleAuditRecord
from backend.models.rule_publication import RulePublication
from backend.models.rule_version import RuleVersion


@event.listens_for(Session, "before_flush")
def prevent_history_mutation(session: Session, flush_context: object, instances: object) -> None:
    for obj in session.dirty:
        state = inspect(obj)
        changed = any(attribute.history.has_changes() for attribute in state.attrs)
        if not changed:
            continue
        if isinstance(obj, (RulePublication, RuleAuditRecord)):
            raise ValueError("Audit/publication records are append-only")
        if isinstance(obj, RuleVersion):
            history = state.attrs.status.history
            previous = history.deleted[0] if history.deleted else obj.status
            if previous in {"APPROVED", "REJECTED"}:
                raise ValueError("Reviewed rule versions are immutable")
    for obj in session.deleted:
        if isinstance(obj, (RulePublication, RuleAuditRecord, RuleVersion)):
            raise ValueError("Historical rule/audit/publication records cannot be deleted")


@event.listens_for(Session, "do_orm_execute")
def prevent_bulk_history_mutation(state: object) -> None:
    from typing import cast

    from sqlalchemy.orm import ORMExecuteState

    execution = cast(ORMExecuteState, state)
    if not (execution.is_update or execution.is_delete):
        return
    table = getattr(execution.statement, "table", None)
    if getattr(table, "schema", None) != "crosstax":
        return
    name = getattr(table, "name", None)
    if name in {"rule_audit_records", "rule_publications"}:
        raise ValueError("Historical records are append-only")
    if name == "rule_versions" and not execution.execution_options.get("rule_candidate_review"):
        raise ValueError("Rule versions can only be reviewed through the candidate transition")
