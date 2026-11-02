"""Rule storage lifecycle and optimistic publication checks."""

import pytest

from backend.infrastructure.exceptions import ConflictException, NotFoundException
from backend.models import RuleEngineState
from backend.repositories.rules import RuleRepository


async def test_version_lifecycle(db_session):
    repository = RuleRepository(db_session)
    db_session.add(RuleEngineState(id=1))
    await db_session.flush()
    with pytest.raises(NotFoundException):
        await repository.get_active_version()
    source = await repository.add_source("Official", "CN", "https://example.org/tin")
    run = await repository.start_sync()
    document = await repository.store_document(source.id, run.id, b"TIN guidance", "text/plain")
    duplicate = await repository.store_document(source.id, run.id, b"TIN guidance", "text/plain")
    assert document.id == duplicate.id
    version = await repository.create_candidate({"CN": {"algorithm": "REGEX_ONLY"}}, [document.id], {})
    with pytest.raises(ConflictException):
        await repository.activate(version.version_id, 0)
    await repository.review_candidate(version.version_id, True, {"passed": True})
    await repository.activate(version.version_id, 0)
    revision, active = await repository.get_active_version()
    assert revision == 1
    assert active.version_id == version.version_id
    with pytest.raises(ConflictException):
        await repository.activate(version.version_id, 0)
    with pytest.raises(ConflictException):
        await repository.review_candidate(version.version_id, False, {})
    await repository.finish_sync(run.id, "SUCCEEDED", {"documents": 1})
    with pytest.raises(ConflictException):
        await repository.finish_sync(run.id, "FAILED", {})
