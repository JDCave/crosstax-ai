"""Scheduled source checks and reviewed rule promotion without a management UI."""

from __future__ import annotations

import hashlib
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.engine.contracts import ValidationPolicy
from backend.engine.impact import ImpactReport, analyze_impact, selectors
from backend.engine.publication import RulePublisher
from backend.engine.regression import run_regressions
from backend.engine.reproducibility import canonical_hash
from backend.engine.rule_loader import RuleLoader, compile_snapshot
from backend.engine.validation import ValidationEngine
from backend.infrastructure.exceptions import ConflictException, NotFoundException
from backend.models import RuleDocument, RuleSource, RuleVersion
from backend.repositories.rules import RuleRepository
from backend.services.rule_import import RuleSourceImporter


class DocumentReference(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    document_id: str = Field(min_length=1, max_length=36)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class RuleBundle(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal[1]
    base_version_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    rules: dict[str, Any]
    documents: list[DocumentReference] = Field(default_factory=list, max_length=100)
    regression_cases: list[dict[str, Any]] | None = Field(default=None, max_length=5000)

    @model_validator(mode="after")
    def unique_documents(self) -> RuleBundle:
        if len({doc.document_id for doc in self.documents}) != len(self.documents):
            raise ValueError("Duplicate document reference")
        return self


class TrustedApproval(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    base_version_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_version_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    impact_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class PublicationPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal[1]
    approvals: list[TrustedApproval] = Field(default_factory=list, max_length=1000)


class UpdateResult(BaseModel):
    run_id: str
    status: Literal[
        "UNCHANGED",
        "METADATA_ONLY",
        "WAITING_FOR_BUNDLE",
        "PLANNED",
        "PENDING_APPROVAL",
        "BLOCKED",
        "PUBLISHED",
        "NO_ACTIVE_RULES",
        "FAILED",
        "CONFLICT",
    ]
    reason_code: str | None = None
    error_type: str | None = None
    base_version_id: str | None = None
    candidate_version_id: str | None = None
    impact: ImpactReport | None = None
    regression: dict[str, Any] | None = None
    evidence_hash: str | None = None
    documents: list[DocumentReference] = Field(default_factory=list)
    source_sync: dict[str, Any] | None = None


class RuleUpdateCoordinator:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        importer: RuleSourceImporter | None = None,
    ) -> None:
        self.sessions = sessions
        self.importer = importer
        self.loader = RuleLoader(sessions)
        self.engine = ValidationEngine(self.loader)
        self.publisher = RulePublisher(sessions)

    async def run(
        self,
        bundle: RuleBundle | None,
        cases: object,
        policy: ValidationPolicy,
        *,
        publication_policy: PublicationPolicy | None = None,
        publish: bool = False,
        sync_sources: bool = True,
        trigger_type: str = "SCHEDULED",
    ) -> UpdateResult:
        async with self.sessions.begin() as session:
            run = await RuleRepository(session).start_sync(trigger_type)
            run_id = run.id
        result = UpdateResult(run_id=run_id, status="FAILED")
        try:
            await self._execute(result, bundle, cases, policy, publication_policy, publish, sync_sources, trigger_type)
        except NotFoundException:
            result.status, result.reason_code = "NO_ACTIVE_RULES", "BOOTSTRAP_REQUIRED"
        except ConflictException:
            result.status, result.reason_code = "CONFLICT", "REVISION_OR_REVIEW_CHANGED"
        except Exception as exc:
            result.status, result.reason_code = "FAILED", "UPDATE_ERROR"
            result.error_type = type(exc).__name__
        terminal = "FAILED" if result.status in {"FAILED", "CONFLICT", "BLOCKED", "NO_ACTIVE_RULES"} else "SUCCEEDED"
        async with self.sessions.begin() as session:
            await RuleRepository(session).finish_sync(run_id, terminal, result.model_dump(mode="json"))
        return result

    async def _execute(
        self,
        result: UpdateResult,
        bundle: RuleBundle | None,
        cases: object,
        policy: ValidationPolicy,
        publication_policy: PublicationPolicy | None,
        publish: bool,
        sync_sources: bool,
        trigger_type: str,
    ) -> None:
        synced: dict[str, str] = {}
        imported_documents: set[str] = set()
        if sync_sources:
            if self.importer is None:
                raise ValueError("No source importer")
            sync = await self.importer.sync(trigger_type)
            rows = sync.get("sources", [])
            if not isinstance(rows, list):
                raise ValueError("Invalid source sync result")
            result.source_sync = {
                "run_id": sync.get("run_id"),
                "status": sync.get("status"),
                "imported": sum(row.get("status") == "IMPORTED" for row in rows),
                "unchanged": sum(row.get("status") == "UNCHANGED" for row in rows),
                "failed": sum(row.get("status") == "FAILED" for row in rows),
            }
            if sync.get("status") != "SUCCEEDED" or not rows:
                result.status = "BLOCKED"
                result.reason_code = "SOURCE_SYNC_FAILED" if rows else "NO_SOURCES_CONFIGURED"
                return
            synced = {row["source_id"]: row["document_id"] for row in rows}
            imported_documents = {row["document_id"] for row in rows if row["status"] == "IMPORTED"}
        if bundle is None:
            result.status, result.reason_code = "WAITING_FOR_BUNDLE", "UPSTREAM_RULES_NOT_AVAILABLE"
            return
        base = await self.loader.refresh()
        candidate_id = canonical_hash(bundle.rules)
        result.base_version_id, result.candidate_version_id = base.version_id, candidate_id
        if imported_documents and not imported_documents <= {doc.document_id for doc in bundle.documents}:
            result.status, result.reason_code = "WAITING_FOR_BUNDLE", "NEW_SOURCE_REQUIRES_UPSTREAM_REVIEW"
            return
        if candidate_id == base.version_id:
            if imported_documents:
                await self._evidence_urls(bundle.documents, synced)
            result.status = "UNCHANGED"
            return
        if bundle.base_version_id != base.version_id:
            result.status, result.reason_code = "BLOCKED", "STALE_BASE_VERSION"
            return
        candidate = compile_snapshot(candidate_id, base.revision + 1, bundle.rules)
        report = analyze_impact(self.engine, base, candidate, cases, policy)
        result.impact = report
        result.documents = sorted(bundle.documents, key=lambda doc: doc.document_id)
        result.evidence_hash = canonical_hash([doc.model_dump() for doc in result.documents])
        if not any(change.execution_changed for change in report.rule_changes):
            result.status = "METADATA_ONLY"
            return
        # References are checked before FK writes; activation also requires changed rules' official URLs.
        evidence_urls = await self._evidence_urls(bundle.documents, synced)
        await self.publisher.register(bundle.rules, [doc.document_id for doc in bundle.documents])
        async with self.sessions() as session:
            version = await session.get(RuleVersion, candidate_id)
            if version is None:
                raise ValueError("Registered candidate disappeared")
            state = version.status
            review = version.validation_report.get("review", {})
            regression_cases = (
                review.get("regression_cases")
                if state == "APPROVED" and isinstance(review, dict)
                else (bundle.regression_cases)
            )
        if state == "REJECTED":
            result.status, result.reason_code = "BLOCKED", "CANDIDATE_REJECTED"
            return
        try:
            result.regression = run_regressions(candidate, regression_cases)
        except ValueError:
            result.status, result.reason_code = "BLOCKED", "REGRESSION_FAILED"
            return
        if report.risks:
            result.status, result.reason_code = "BLOCKED", "IMPACT_REQUIRES_MANUAL_PUBLICATION"
            return
        if not publish:
            result.status = "PLANNED"
            return
        if state != "APPROVED":
            result.status, result.reason_code = "PENDING_APPROVAL", "CANDIDATE_NOT_APPROVED"
            return
        changed_rules = [
            selectors(candidate)[change.selector]
            for change in report.rule_changes
            if change.execution_changed and change.change != "REMOVED"
        ]
        required_urls = {
            (url, change.selector[0])
            for change in report.rule_changes
            if change.execution_changed and change.change != "REMOVED"
            for rule in [selectors(candidate)[change.selector]]
            for url in (rule.source_url, rule.algorithm_source_url)
            if url
        }
        if (
            not changed_rules
            or any(rule.source_url is None for rule in changed_rules)
            or not required_urls <= evidence_urls
        ):
            result.status, result.reason_code = "BLOCKED", "MISSING_CURRENT_SOURCE_EVIDENCE"
            return
        trusted = publication_policy and any(
            approval.base_version_id == base.version_id
            and approval.candidate_version_id == candidate_id
            and approval.impact_hash == report.report_hash
            and approval.evidence_hash == result.evidence_hash
            for approval in publication_policy.approvals
        )
        if not trusted:
            result.status, result.reason_code = "PENDING_APPROVAL", "NO_TRUSTED_APPROVAL"
            return
        await self.publisher.activate(
            candidate_id,
            base.revision,
            actor="rule-update-job",
            reason=f"run={result.run_id} impact={report.report_hash} evidence={result.evidence_hash}",
        )
        result.status = "PUBLISHED"

    async def _evidence_urls(self, references: list[DocumentReference], synced: dict[str, str]) -> set[tuple[str, str]]:
        urls = set()
        async with self.sessions() as session:
            for ref in references:
                row = (
                    await session.execute(
                        select(RuleDocument, RuleSource)
                        .join(RuleSource, RuleSource.id == RuleDocument.source_id)
                        .where(RuleDocument.id == ref.document_id)
                    )
                ).one_or_none()
                if row is None:
                    raise ValueError("Referenced document is missing")
                document, source = row
                if (
                    document.content_hash != ref.content_hash
                    or hashlib.sha256(document.raw_content).hexdigest() != ref.content_hash
                ):
                    raise ValueError("Document content differs from reference hash")
                if not source.enabled:
                    raise ValueError("Source is disabled")
                if source.id in synced:
                    latest = synced[source.id] == document.id
                else:
                    recent = list(
                        (
                            await session.scalars(
                                select(RuleDocument)
                                .where(RuleDocument.source_id == source.id)
                                .order_by(RuleDocument.fetched_at.desc())
                                .limit(2)
                            )
                        ).all()
                    )
                    latest = bool(recent) and recent[0].id == document.id
                    if len(recent) == 2 and recent[0].fetched_at == recent[1].fetched_at:
                        latest = False  # Ambiguous timestamp order: require a fresh sync rather than guess.
                if latest:
                    urls.add((source.url, source.jurisdiction_code))
        return urls
