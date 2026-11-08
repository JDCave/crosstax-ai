"""Document import, conditional requests, and failure isolation."""

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.models import Base, RuleDocument, RuleSource, RuleSyncRun
from backend.services.rule_import import RuleSourceImporter, SourceDefinition


@pytest.fixture
async def sessions():
    engine = create_async_engine("sqlite+aiosqlite://", execution_options={"schema_translate_map": {"crosstax": None}})
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


def definition(code="CN", path="china"):
    return SourceDefinition(name=path, jurisdiction_code=code, url=f"https://www.oecd.org/{path}.pdf")


async def test_import_is_idempotent_and_uses_cache(sessions):
    requests = []

    def respond(request):
        requests.append(request)
        if request.headers.get("if-none-match"):
            return httpx.Response(304)
        return httpx.Response(
            200, content=b"%PDF-1.7 test", headers={"content-type": "application/pdf", "etag": '"v1"'}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        importer = RuleSourceImporter(sessions, client)
        assert await importer.register([definition()]) == 1
        assert await importer.register([definition()]) == 0
        first = await importer.sync()
        second = await importer.sync()
        assert first["sources"][0]["status"] == "IMPORTED"
        assert second["sources"][0]["status"] == "UNCHANGED"
        assert requests[1].headers["if-none-match"] == '"v1"'
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(RuleDocument)) == 1
        assert await session.scalar(select(func.count()).select_from(RuleSyncRun)) == 2


async def test_one_source_failure_does_not_undo_success(sessions):
    def respond(request):
        if "china" in request.url.path:
            return httpx.Response(500)
        return httpx.Response(200, content=b"%PDF-1.7 good", headers={"content-type": "application/pdf"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        importer = RuleSourceImporter(sessions, client)
        await importer.register([definition(), definition("SG", "singapore")])
        assert (await importer.sync())["status"] == "PARTIAL"
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(RuleDocument)) == 1


async def test_redirect_and_size_limits(sessions):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(302, headers={"location": "http://localhost/internal"}))
    ) as client:
        importer = RuleSourceImporter(sessions, client)
        await importer.register([definition()])
        assert (await importer.sync())["status"] == "FAILED"
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(200, content=b"%PDF-1.7 too big", headers={"content-type": "application/pdf"})
        )
    ) as client:
        importer = RuleSourceImporter(sessions, client, max_bytes=4)
        assert (await importer.sync())["status"] == "FAILED"


async def test_invalid_manifest_is_atomic(sessions):
    async with httpx.AsyncClient() as client:
        importer = RuleSourceImporter(sessions, client)
        bad = SourceDefinition(name="bad", jurisdiction_code="SG", url="https://example.org/rules")
        with pytest.raises(ValueError):
            await importer.register([definition(), bad])
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(RuleSource)) == 0
