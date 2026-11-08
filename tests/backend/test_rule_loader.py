"""Invalid reload isolation and version-bound snapshots."""

import hashlib
import json
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from backend.engine.rule_loader import RuleLoader, compile_snapshot
from backend.models import RuleVersion


def version(rules):
    digest = hashlib.sha256(
        json.dumps(rules, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    return RuleVersion(version_id=digest, rules=rules, status="APPROVED", schema_version=1)


def test_compilation_checks_and_immutability():
    rules = {"CN": {"regex": "[0-9]{18}", "algorithm": "MOD11_2"}}
    row = version(rules)
    snapshot = compile_snapshot(row.version_id, 1, rules)
    assert snapshot.rules["CN"].pattern.fullmatch("1" * 18)
    with pytest.raises(TypeError):
        snapshot.rules["HK"] = snapshot.rules["CN"]
    with pytest.raises(ValueError, match="hash"):
        compile_snapshot("0" * 64, 1, rules)
    malformed = {"CN": {"regex": "[", "algorithm": "UNKNOWN"}}
    with pytest.raises(ValidationError):
        compile_snapshot(version(malformed).version_id, 1, malformed)


async def test_reload_failure_preserves_snapshot_and_old_audit():
    sessions = AsyncMock()
    sessions.return_value.__aenter__ = AsyncMock()
    # A session factory is synchronous; its returned context manager is async.
    from unittest.mock import MagicMock

    factory = MagicMock(return_value=sessions.return_value)
    loader = RuleLoader(factory)
    old_version = version({"CN": {"regex": "[0-9]{18}", "algorithm": "MOD11_2"}})
    new_version = version({"HK": {"regex": "[0-9]{8}", "algorithm": "REGEX_ONLY"}})
    with patch("backend.engine.rule_loader.RuleRepository") as repository:
        repository.return_value.get_active_version = AsyncMock(return_value=(1, old_version))
        old_snapshot = await loader.refresh()
        repository.return_value.get_active_version.return_value = (2, new_version)
        assert (await loader.refresh()).version_id == new_version.version_id
        assert "CN" in old_snapshot.rules
        repository.return_value.get_active_version.return_value = (3, version({}))
        with pytest.raises(ValueError):
            await loader.refresh()
        assert loader.current().version_id == new_version.version_id
        repository.return_value.get_active_version.return_value = (1, old_version)
        assert (await loader.refresh()).revision == 2
