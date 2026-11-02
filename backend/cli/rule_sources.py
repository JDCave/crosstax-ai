"""Run with python -m backend.cli.rule_sources --help."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

import httpx
from pydantic import TypeAdapter

from backend.infrastructure.database import async_session_factory, engine
from backend.services.rule_import import RuleSourceImporter, SourceDefinition


async def main() -> None:
    parser = argparse.ArgumentParser(description="Register and import official rule source documents")
    parser.add_argument("--manifest", type=Path, help="Register sources from a JSON array (idempotent)")
    parser.add_argument("--sync", action="store_true", help="Fetch all enabled sources")
    parser.add_argument("--scheduled", action="store_true", help="Record a scheduled rather than manual sync")
    args = parser.parse_args()
    if not args.manifest and not args.sync:
        parser.error("Specify --manifest and/or --sync")
    try:
        async with httpx.AsyncClient(headers={"User-Agent": "CrossTaxAI-RuleSync/0.1"}) as client:
            importer = RuleSourceImporter(async_session_factory, client)
            if args.manifest:
                definitions = TypeAdapter(list[SourceDefinition]).validate_json(args.manifest.read_text())
                print(json.dumps({"registered": await importer.register(definitions)}))
            if args.sync:
                result = await importer.sync("SCHEDULED" if args.scheduled else "MANUAL")
                print(json.dumps(result, ensure_ascii=False))
                if result["status"] != "SUCCEEDED":
                    raise SystemExit(1)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
