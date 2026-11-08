"""Conservative regex subset and catalog bundle bounds."""

import pytest

from backend.cli.demo_cases import snapshot
from backend.engine.rule_safety import check_pattern


@pytest.mark.parametrize("pattern", ["(a+)+", "(a|aa)+", r"(a)\1", "a{1,}", "a{1000}", "a?" * 20, "a{0,64}" * 4])
def test_unsafe_or_excessive_patterns_are_rejected(pattern):
    with pytest.raises(ValueError):
        check_pattern(pattern)


def test_ordinary_bounded_identifier_patterns_and_limits():
    check_pattern(r"[A-Z]{1,2}[0-9]{6}[0-9A]")
    check_pattern(r"(?!000|666|9[0-9]{2})[0-9]{3}(?!00)[0-9]{2}(?!0000)[0-9]{4}")
    with pytest.raises(ValueError, match="512"):
        check_pattern("A" * 513)
    with pytest.raises(ValueError, match="1 MiB"):
        snapshot({"CN": {"regex": "A" * 1_048_576, "algorithm": "REGEX_ONLY"}}, 1)
