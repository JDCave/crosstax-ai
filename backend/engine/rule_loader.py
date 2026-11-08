"""Validate database rules and atomically expose immutable audit snapshots."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from threading import Lock
from types import MappingProxyType
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.engine.rule_safety import check_pattern
from backend.repositories.rules import RuleRepository

Algorithm = Literal[
    "MOD11_2",
    "HKID_WEIGHT",
    "NRIC_WEIGHT",
    "REGEX_ONLY",
    "NL_MOD11",
    "PL_NIP",
    "PL_PESEL",
    "AU_ABN",
    "NO_ORGNR",
    "JP_CORPORATE",
    "CA_SIN",
    "ES_NIF_NIE",
]


class JurisdictionRule(BaseModel):
    """Existing jurisdiction-keyed JSON contract from specs/data-spec.md."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    regex: str = Field(min_length=1)
    algorithm: Algorithm


class TypedRule(JurisdictionRule):
    rule_id: str = Field(min_length=1)
    holder_type: Literal["INDIVIDUAL", "ENTITY"]
    tin_type: str = Field(min_length=1)
    source_url: str = Field(pattern=r"^https://")
    source_section: str = Field(min_length=1)
    verification_level: Literal["FORMAT_ONLY", "CHECKSUM"]
    algorithm_source_url: str | None = Field(default=None, pattern=r"^https://")
    reviewed_on: str | None = None
    limitations: str | None = None


class TypedRuleset(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal[2]
    jurisdictions: dict[str, list[TypedRule]]


@dataclass(frozen=True)
class CompiledRule:
    algorithm: Algorithm
    pattern: re.Pattern[str]
    rule_id: str | None = None
    verification_level: str = "FORMAT_ONLY"
    source_url: str | None = None
    algorithm_source_url: str | None = None
    source_section: str | None = None
    limitations: str | None = None


@dataclass(frozen=True)
class RuleSnapshot:
    version_id: str
    revision: int
    rules: MappingProxyType[str, CompiledRule]
    variants: MappingProxyType[tuple[str, str, str], CompiledRule] = field(default_factory=lambda: MappingProxyType({}))


def compile_snapshot(version_id: str, revision: int, rules: dict[str, object]) -> RuleSnapshot:
    """Validate the complete snapshot before replacing anything in memory."""
    canonical = json.dumps(rules, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    if len(canonical.encode("utf-8")) > 1_048_576:
        raise ValueError("Rule bundle exceeds 1 MiB")
    if hashlib.sha256(canonical.encode("utf-8")).hexdigest() != version_id:
        raise ValueError("Rule content does not match version hash")
    if rules.get("schema_version") == 2:
        typed = TypedRuleset.model_validate(rules)
        if sum(len(entries) for entries in typed.jurisdictions.values()) > 1000:
            raise ValueError("Rule bundle exceeds 1000 variants")
        variants: dict[tuple[str, str, str], CompiledRule] = {}
        ids: set[str] = set()
        if not typed.jurisdictions:
            raise ValueError("Empty ruleset cannot be activated")
        for code, entries in typed.jurisdictions.items():
            if re.fullmatch(r"[A-Z]{2}", code) is None or not entries:
                raise ValueError("Invalid jurisdiction or empty variants")
            for entry in entries:
                key = (code, entry.holder_type, entry.tin_type)
                if key in variants or entry.rule_id in ids:
                    raise ValueError("Duplicate rule selector or rule ID")
                if (entry.algorithm == "REGEX_ONLY") != (entry.verification_level == "FORMAT_ONLY"):
                    raise ValueError("Verification level contradicts algorithm")
                check_pattern(entry.regex)
                variants[key] = CompiledRule(
                    entry.algorithm,
                    re.compile(entry.regex),
                    entry.rule_id,
                    entry.verification_level,
                    entry.source_url,
                    entry.algorithm_source_url,
                    entry.source_section,
                    entry.limitations,
                )
                ids.add(entry.rule_id)
        return RuleSnapshot(version_id, revision, MappingProxyType({}), MappingProxyType(variants))
    parsed = TypeAdapter(dict[str, JurisdictionRule]).validate_python(rules)
    if not parsed:
        raise ValueError("Empty ruleset cannot be activated")
    compiled: dict[str, CompiledRule] = {}
    for code, rule in parsed.items():
        if re.fullmatch(r"[A-Z]{2}", code) is None:
            raise ValueError("Jurisdiction must be an uppercase two-letter code")
        check_pattern(rule.regex)
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
            if version.status != "APPROVED" or version.schema_version not in (1, 2):
                raise ValueError("Active rules must be approved with schema_version 1 or 2")
            if version.schema_version != version.rules.get("schema_version", 1):
                raise ValueError("Stored schema version differs from rule content")
            # Still verify database content on every read; reuse compiled objects only after hash verification.
            canonical = json.dumps(
                version.rules, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
            )
            if hashlib.sha256(canonical.encode("utf-8")).hexdigest() != version.version_id:
                raise ValueError("Rule content does not match version hash")
            with self._lock:
                if self._snapshot is not None and self._snapshot.version_id == version.version_id:
                    if revision > self._snapshot.revision:
                        from dataclasses import replace

                        self._snapshot = replace(self._snapshot, revision=revision)
                    return self._snapshot
            candidate = compile_snapshot(version.version_id, revision, version.rules)
        with self._lock:
            # A slower concurrent refresh must not undo a newer publication.
            if self._snapshot is None or candidate.revision > self._snapshot.revision:
                self._snapshot = candidate
            elif candidate.revision == self._snapshot.revision and candidate.version_id != self._snapshot.version_id:
                raise ValueError("Different versions share the same publication revision")
            return self._snapshot
