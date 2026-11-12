"""Five synthetic audit paths and database-backed rule publication."""

from datetime import date

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.engine.completeness import check_completeness
from backend.engine.contracts import AuditIssue, CRSFormData, ValidationPolicy
from backend.engine.regulatory_parameters import load_form_policy
from backend.engine.rule_loader import RuleLoader
from backend.engine.validation import ValidationEngine
from backend.models import RuleEngineState
from backend.repositories.rules import RuleRepository


def form(**changes):
    values = dict(
        holder_name="Demo",
        holder_dob="2000-01-01",
        residence_address="Demo address",
        jurisdiction_code="CN",
        tin="11010519491231002X",
        has_no_tin=False,
        has_signature=True,
        signing_date="2026-11-01",
    )
    return CRSFormData.model_validate(values | changes)


POLICY = ValidationPolicy(today=date(2026, 11, 2), earliest_signing_date=date(2020, 1, 1))
# The threshold is a regulatory parameter (FR-041): the test reads the same
# rules/hk/form_policy.json the engine does instead of asserting a private constant.
REASON_B_MIN = load_form_policy()[0]["reason_b_min_length"]


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"signing_date": "2026-11-03"}, "INVALID_DATE"),
        ({"signing_date": "2026-02-30"}, "INVALID_DATE"),
        ({"signing_date": "20261101"}, "INVALID_DATE"),
        ({"signing_date": None}, "INVALID_DATE"),
        ({"signing_date": "2019-12-31"}, "INVALID_DATE"),
        ({"has_signature": False}, "NO_SIGNATURE"),
        ({"has_no_tin": True}, "MISSING_REASON"),
        ({"has_no_tin": True, "tin_reason_code": "B", "tin_reason_explanation": "    "}, "MISSING_REASON"),
    ],
)
def test_completeness(changes, code):
    assert code in {issue.code for issue in check_completeness(form(**changes), POLICY, REASON_B_MIN)}


@pytest.mark.parametrize("reason", ["A", "B", "C"])
def test_valid_exemption(reason):
    assert (
        check_completeness(
            form(has_no_tin=True, tin=None, tin_reason_code=reason, tin_reason_explanation="Explanation"),
            POLICY,
            REASON_B_MIN,
        )
        == []
    )


def test_rejects_coerced_boolean():
    with pytest.raises(ValidationError):
        form(has_signature="false")


async def test_five_paths_and_hot_reload(test_engine):
    sessions = async_sessionmaker(test_engine, expire_on_commit=False)
    async with sessions.begin() as session:
        session.add(RuleEngineState(id=1))
        repository = RuleRepository(session)
        first = await repository.create_candidate({"CN": {"regex": "[0-9]{17}[0-9X]", "algorithm": "MOD11_2"}}, [], {})
        await repository.review_candidate(first.version_id, True, {"passed": True})
        await repository.activate(first.version_id, 0)
        first_id = first.version_id
    try:
        engine = ValidationEngine(RuleLoader(sessions))
        warning = AuditIssue(
            code="INDICIA_CONFLICT",
            severity="WARNING",
            field="holder_name",
            message="Demo upstream conflict",
            confidence=0.9,
        )
        # Synthetic A-D: pass, checksum blocker, missing signature, upstream warning.
        assert (await engine.validate(form(), POLICY)).verdict == "AUTO_PASS"
        assert (await engine.validate(form(tin="110105194912310021"), POLICY)).verdict == "NEED_USER_FIX"
        assert (await engine.validate(form(has_signature=False), POLICY, [warning])).verdict == "NEED_USER_FIX"
        result = await engine.validate(form(), POLICY, [warning])
        assert result.verdict == "MANUAL_TRIAGE"
        assert result.rule_version_id == first_id
        assert (
            await engine.validate(form(has_no_tin=True, tin=None, tin_reason_code="A"), POLICY)
        ).verdict == "MANUAL_TRIAGE"
        retained_snapshot = engine.loader.current()
        # Synthetic E: a deliberately stricter test-only configuration.
        async with sessions.begin() as session:
            repository = RuleRepository(session)
            second = await repository.create_candidate(
                {"CN": {"regex": "[0-9]{18}", "algorithm": "REGEX_ONLY"}}, [], {}
            )
            await repository.review_candidate(second.version_id, True, {"passed": True})
            await repository.activate(second.version_id, 1)
        assert (await engine.validate(form(), POLICY)).verdict == "NEED_USER_FIX"
        assert engine.validate_snapshot(form(), POLICY, retained_snapshot).verdict == "AUTO_PASS"
    finally:
        # This session-scoped fixture is shared: leave it clean for other tests.
        from sqlalchemy import delete

        from backend.models import RuleVersion

        async with sessions.begin() as session:
            await session.execute(delete(RuleEngineState))
            # Test-only cleanup through Core; supported application writes use guarded ORM sessions.
            connection = await session.connection()
            await connection.execute(delete(RuleVersion))
