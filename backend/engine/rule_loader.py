"""Validate database rules and atomically expose immutable audit snapshots."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from threading import Lock
from types import MappingProxyType
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.repositories.rules import RuleRepository

Algorithm = Literal["MOD11_2", "HKID_WEIGHT", "NRIC_WEIGHT", "REGEX_ONLY"]


class JurisdictionRule(BaseModel):
    """Existing jurisdiction-keyed JSON contract from specs/data-spec.md."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    regex: str = Field(min_length=1)
    algorithm: Algorithm


@dataclass(frozen=True)
class CompiledRule:
    algorithm: Algorithm
    pattern: re.Pattern[str]


@dataclass(frozen=True)
class RuleSnapshot:
    version_id: str
    revision: int
    rules: MappingProxyType[str, CompiledRule]


def compile_snapshot(version_id: str, revision: int, rules: dict[str, object]) -> RuleSnapshot:
    """Validate the complete snapshot before replacing anything in memory."""
    canonical = json.dumps(rules, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    if hashlib.sha256(canonical.encode("utf-8")).hexdigest() != version_id:
        raise ValueError("Rule content does not match version hash")
    parsed = TypeAdapter(dict[str, JurisdictionRule]).validate_python(rules)
    if not parsed:
        raise ValueError("Empty ruleset cannot be activated")
    compiled: dict[str, CompiledRule] = {}
    for code, rule in parsed.items():
        if re.fullmatch(r"[A-Z]{2}", code) is None:
            raise ValueError("Jurisdiction must be an uppercase two-letter code")
        compiled[code] = CompiledRule(rule.algorithm, re.compile(rule.regex))
    return RuleSnapshot(version_id, revision, MappingProxyType(compiled))


class RuleLoader:
    """One loader per application process; audit callers retain returned snapshots."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions
        self._lock = Lock()
        self._snapshot: RuleSnapshot | None = None

    def current(self) -> RuleSnapshot:
        with self._lock:
            if self._snapshot is None:
                raise RuntimeError("No rule snapshot loaded")
            return self._snapshot

    async def refresh(self) -> RuleSnapshot:
        """Raise on invalid active data, retaining the previous valid snapshot."""
        async with self.sessions() as session:
            revision, version = await RuleRepository(session).get_active_version()
            if version.status != "APPROVED" or version.schema_version != 1:
                raise ValueError("Active rules must be approved with schema_version=1")
            candidate = compile_snapshot(version.version_id, revision, version.rules)
        with self._lock:
            # A slower concurrent refresh must not undo a newer publication.
            if self._snapshot is None or candidate.revision > self._snapshot.revision:
                self._snapshot = candidate
            elif candidate.revision == self._snapshot.revision and candidate.version_id != self._snapshot.version_id:
                raise ValueError("Different versions share the same publication revision")
            return self._snapshot
