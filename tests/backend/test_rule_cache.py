"""Reuse compiled rules without ignoring corrupted database content."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.cli.demo_cases import snapshot
from backend.engine.rule_loader import RuleLoader
from backend.models import RuleVersion


async def test_cache_reuses_compilation_but_checks_content_hash():
    context = AsyncMock()
    loader = RuleLoader(MagicMock(return_value=context))
    rules = {"CN": {"regex": "[0-9]{18}", "algorithm": "REGEX_ONLY"}}
    compiled = snapshot(rules, 1)
    row = RuleVersion(version_id=compiled.version_id, rules=rules, schema_version=1, status="APPROVED")
    with patch("backend.engine.rule_loader.RuleRepository") as repository:
        repository.return_value.get_active_version = AsyncMock(return_value=(1, row))
        first = await loader.refresh()
        with patch("backend.engine.rule_loader.compile_snapshot", side_effect=AssertionError("unnecessary compile")):
            assert await loader.refresh() is first
        row.rules = {"CN": {"regex": "[0-9]{19}", "algorithm": "REGEX_ONLY"}}
        with pytest.raises(ValueError, match="hash"):
            await loader.refresh()
        assert loader.current() is first
