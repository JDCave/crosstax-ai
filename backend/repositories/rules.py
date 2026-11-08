"""Rule persistence operations. The caller owns commit/rollback boundaries."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

from sqlalchemy import CursorResult, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.db import immutability  # noqa: F401 -- register ORM history guards
from backend.infrastructure.exceptions import ConflictException, NotFoundException
from backend.models import RuleDocument, RuleEngineState, RuleSource, RuleSyncRun, RuleVersion, RuleVersionDocument


class RuleRepository:
    """Store sources and candidates; publish approved immutable snapshots."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add_source(self, name: str, jurisdiction_code: str, url: str) -> RuleSource:
        source = RuleSource(id=str(uuid4()), name=name, jurisdiction_code=jurisdiction_code.upper(), url=url)
        self.session.add(source)
        await self.session.flush()
        return source

    async def list_sources(self) -> list[RuleSource]:
        return list((await self.session.scalars(select(RuleSource).where(RuleSource.enabled.is_(True)))).all())

    async def start_sync(self, trigger_type: str = "MANUAL") -> RuleSyncRun:
        run = RuleSyncRun(id=str(uuid4()), trigger_type=trigger_type, summary={})
        self.session.add(run)
        await self.session.flush()
        return run

    async def finish_sync(
        self, run_id: str, status: str, summary: dict[str, object], error_message: str | None = None
    ) -> None:
        if status not in {"SUCCEEDED", "PARTIAL", "FAILED"}:
            raise ValueError("Invalid terminal sync status")
        result = await self.session.execute(
            update(RuleSyncRun)
            .where(RuleSyncRun.id == run_id, RuleSyncRun.status == "RUNNING")
            .values(status=status, summary=summary, error_message=error_message, finished_at=datetime.now(UTC))
        )
        if cast(CursorResult[tuple[object, ...]], result).rowcount != 1:
            raise ConflictException("Sync task is missing or already finished")

    async def store_document(
        self, source_id: str, run_id: str, content: bytes, content_type: str, extracted_text: str | None = None
    ) -> RuleDocument:
        digest = hashlib.sha256(content).hexdigest()
        existing = await self.session.scalar(
            select(RuleDocument).where(RuleDocument.source_id == source_id, RuleDocument.content_hash == digest)
        )
        if existing is not None:
            return existing
        document = RuleDocument(
            id=str(uuid4()),
            source_id=source_id,
            sync_run_id=run_id,
            content_hash=digest,
            content_type=content_type,
            raw_content=content,
            extracted_text=extracted_text,
        )
        self.session.add(document)
        await self.session.flush()
        return document

    async def create_candidate(
        self, rules: dict[str, object], document_ids: list[str], extraction_metadata: dict[str, object]
    ) -> RuleVersion:
        canonical = json.dumps(rules, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        existing = await self.session.get(RuleVersion, digest)
        if existing is not None:
            return existing
        version = RuleVersion(
            version_id=digest,
            rules=json.loads(canonical),
            validation_report={},
            extraction_metadata=extraction_metadata,
        )
        self.session.add(version)
        await self.session.flush()
        for document_id in set(document_ids):
            self.session.add(RuleVersionDocument(version_id=digest, document_id=document_id))
        await self.session.flush()
        return version

    async def review_candidate(self, version_id: str, approved: bool, report: dict[str, object]) -> None:
        result = await self.session.execute(
            update(RuleVersion)
            .execution_options(rule_candidate_review=True)
            .where(RuleVersion.version_id == version_id, RuleVersion.status == "CANDIDATE")
            .values(
                status="APPROVED" if approved else "REJECTED",
                validation_report=report,
                approved_at=datetime.now(UTC) if approved else None,
            )
        )
        if cast(CursorResult[tuple[object, ...]], result).rowcount != 1:
            raise ConflictException("Version is missing or has already been reviewed")

    async def activate(self, version_id: str, expected_revision: int) -> None:
        version = await self.session.get(RuleVersion, version_id)
        if version is None:
            raise NotFoundException("Rule version not found")
        if version.status != "APPROVED":
            raise ConflictException("Only approved versions can be activated")
        result = await self.session.execute(
            update(RuleEngineState)
            .where(RuleEngineState.id == 1, RuleEngineState.revision == expected_revision)
            .values(active_version_id=version_id, revision=RuleEngineState.revision + 1, activated_at=datetime.now(UTC))
        )
        if cast(CursorResult[tuple[object, ...]], result).rowcount != 1:
            raise ConflictException("Rule publication revision changed or state row is missing")

    async def get_active_version(self) -> tuple[int, RuleVersion]:
        row = (
            await self.session.execute(
                select(RuleEngineState.revision, RuleVersion)
                .join(RuleVersion, RuleEngineState.active_version_id == RuleVersion.version_id)
                .where(RuleEngineState.id == 1)
            )
        ).one_or_none()
        if row is None:
            raise NotFoundException("No active rule version")
        return row[0], row[1]
