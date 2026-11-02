"""Bounded official-document import with short database transactions."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urljoin, urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.models import RuleDocument, RuleSource
from backend.repositories.rules import RuleRepository


class SourceDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=200)
    jurisdiction_code: str = Field(pattern=r"^[A-Z]{2}$")
    url: str


def validate_url(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != "www.oecd.org" or parsed.port not in (None, 443):
        raise ValueError("Only https://www.oecd.org official sources are supported")
    if parsed.username or parsed.password or parsed.fragment:
        raise ValueError("Source URL must not contain credentials or fragments")


@dataclass(frozen=True)
class FetchResult:
    content: bytes | None
    content_type: str
    etag: str | None
    last_modified: str | None


class RuleSourceImporter:
    """Import raw source documents; rule extraction/publication is a separate stage."""

    def __init__(
        self, sessions: async_sessionmaker[AsyncSession], client: httpx.AsyncClient, max_bytes: int = 10 * 1024 * 1024
    ) -> None:
        self.sessions = sessions
        self.client = client
        self.max_bytes = max_bytes

    async def register(self, definitions: list[SourceDefinition]) -> int:
        for definition in definitions:
            validate_url(definition.url)
        count = 0
        async with self.sessions.begin() as session:
            for definition in definitions:
                existing = await session.scalar(select(RuleSource).where(RuleSource.url == definition.url))
                if existing is None:
                    await RuleRepository(session).add_source(**definition.model_dump())
                    count += 1
                elif existing.jurisdiction_code != definition.jurisdiction_code:
                    raise ValueError("Existing URL has a different jurisdiction")
        return count

    async def fetch(self, source: RuleSource) -> FetchResult:
        headers = {}
        if source.etag:
            headers["If-None-Match"] = source.etag
        if source.last_modified:
            headers["If-Modified-Since"] = source.last_modified
        url = source.url
        for _ in range(4):
            validate_url(url)
            async with self.client.stream("GET", url, headers=headers, follow_redirects=False, timeout=20) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    url = urljoin(url, response.headers["location"])
                    continue
                if response.status_code == 304:
                    return FetchResult(None, "", response.headers.get("etag"), response.headers.get("last-modified"))
                response.raise_for_status()
                mime = response.headers.get("content-type", "").split(";")[0].strip().lower()
                if mime not in {"application/pdf", "text/html", "text/plain"}:
                    raise ValueError("Unsupported source content type")
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    content.extend(chunk)
                    if len(content) > self.max_bytes:
                        raise ValueError("Source exceeds download size limit")
                if not content:
                    raise ValueError("Empty source document")
                if mime == "application/pdf" and not content.startswith(b"%PDF-"):
                    raise ValueError("Invalid PDF signature")
                return FetchResult(
                    bytes(content), mime, response.headers.get("etag"), response.headers.get("last-modified")
                )
        raise ValueError("Too many redirects")

    async def sync(self, trigger_type: str = "MANUAL") -> dict[str, object]:
        async with self.sessions.begin() as session:
            repository = RuleRepository(session)
            run = await repository.start_sync(trigger_type)
            run_id = run.id
            sources = await repository.list_sources()
        results: list[dict[str, object]] = []
        for source in sources:
            try:
                for attempt in range(2):
                    try:
                        fetched = await self.fetch(source)
                        break
                    except (httpx.TimeoutException, httpx.NetworkError):
                        if attempt:
                            raise
                        await asyncio.sleep(0.25)
                async with self.sessions.begin() as session:
                    current = await session.get(RuleSource, source.id)
                    if current is None:
                        raise ValueError("Source no longer exists")
                    if fetched.content is None:
                        document = await session.scalar(
                            select(RuleDocument)
                            .where(RuleDocument.source_id == source.id)
                            .order_by(RuleDocument.fetched_at.desc())
                            .limit(1)
                        )
                        if document is None:
                            raise ValueError("304 response without an imported document")
                        state = "UNCHANGED"
                    else:
                        import hashlib

                        digest = hashlib.sha256(fetched.content).hexdigest()
                        exists = await session.scalar(
                            select(RuleDocument.id).where(
                                RuleDocument.source_id == source.id, RuleDocument.content_hash == digest
                            )
                        )
                        document = await RuleRepository(session).store_document(
                            source.id,
                            run_id,
                            fetched.content,
                            fetched.content_type,
                            fetched.content.decode("utf-8", errors="replace")
                            if fetched.content_type == "text/plain"
                            else None,
                        )
                        state = "UNCHANGED" if exists else "IMPORTED"
                    if fetched.content is not None:
                        current.etag = fetched.etag
                        current.last_modified = fetched.last_modified
                    current.last_checked_at = datetime.now(UTC)
                results.append({"source_id": source.id, "document_id": document.id, "status": state})
            except Exception as exc:
                results.append(
                    {"source_id": source.id, "status": "FAILED", "error": type(exc).__name__ + ": " + str(exc)}
                )
        failures = sum(row["status"] == "FAILED" for row in results)
        status = "SUCCEEDED" if not failures else ("FAILED" if failures == len(results) else "PARTIAL")
        summary: dict[str, object] = {"run_id": run_id, "status": status, "sources": results}
        async with self.sessions.begin() as session:
            await RuleRepository(session).finish_sync(run_id, status, summary)
        return summary
