"""Deterministic execution identity for immutable deployed engine builds."""

from __future__ import annotations

import hashlib
import json
import platform
from collections.abc import Sequence
from functools import lru_cache
from importlib.metadata import version
from pathlib import Path

from backend.engine.contracts import AuditIssue, CRSFormData, ValidationPolicy


def canonical_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    ).hexdigest()


@lru_cache(maxsize=1)
def engine_build_id() -> str:
    """Includes operator source and interpreter/model-validation runtime versions."""
    sources = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(Path(__file__).parent.glob("*.py"))
    }
    return canonical_hash(
        {
            "sources": sources,
            "python": platform.python_version(),
            "pydantic": version("pydantic"),
            "sqlalchemy": version("sqlalchemy"),
        }
    )


def input_fingerprint(form: CRSFormData, policy: ValidationPolicy, issues: Sequence[AuditIssue]) -> str:
    return canonical_hash(
        {
            "form": form.model_dump(mode="json"),
            "policy": policy.model_dump(mode="json"),
            "indicia_issues": [issue.model_dump(mode="json") for issue in issues],
        }
    )
