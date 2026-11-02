"""Explicit commands for structured rule registration and JSON validation."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import cast

from backend.engine.contracts import CRSFormData, ValidationPolicy
from backend.engine.publication import RulePublisher
from backend.engine.rule_loader import RuleLoader
from backend.engine.validation import ValidationEngine
from backend.infrastructure.database import async_session_factory, engine


def read_object(path: Path) -> dict[str, object]:
    value: object = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object")
    return cast(dict[str, object], value)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Versioned rule engine")
    commands = parser.add_subparsers(dest="command", required=True)
    register = commands.add_parser("register", help="Validate and store candidate rules")
    register.add_argument("file", type=Path)
    register.add_argument("--document-id", action="append", default=[])
    approve = commands.add_parser("approve", help="Approve a previously reviewed candidate")
    approve.add_argument("version")
    approve.add_argument("--report", type=Path, required=True)
    activate = commands.add_parser("activate", help="Activate approved version or roll back")
    activate.add_argument("version")
    activate.add_argument("--revision", type=int, required=True)
    commands.add_parser("current")
    commands.add_parser("coverage", help="List active jurisdiction/type rules and official sources")
    validate = commands.add_parser("validate", help="Validate structured CRS JSON")
    validate.add_argument("file", type=Path)
    validate.add_argument("--today", required=True, help="Business date YYYY-MM-DD")
    validate.add_argument("--earliest-date", help="Agreed signing date cutoff YYYY-MM-DD")
    args = parser.parse_args()
    publisher = RulePublisher(async_session_factory)
    try:
        if args.command == "register":
            print(await publisher.register(read_object(args.file), args.document_id))
        elif args.command == "approve":
            await publisher.approve(args.version, read_object(args.report))
            print("APPROVED")
        elif args.command == "activate":
            await publisher.activate(args.version, args.revision)
            print("ACTIVATED")
        else:
            loader = RuleLoader(async_session_factory)
            if args.command == "coverage":
                loaded = await loader.refresh()
                print(
                    json.dumps(
                        [
                            {
                                "jurisdiction_code": key[0],
                                "holder_type": key[1],
                                "tin_type": key[2],
                                "rule_id": rule.rule_id,
                                "verification_level": rule.verification_level,
                                "source_url": rule.source_url,
                            }
                            for key, rule in loaded.variants.items()
                        ],
                        ensure_ascii=False,
                        indent=2,
                    )
                )
            elif args.command == "current":
                snapshot = await loader.refresh()
                print(json.dumps({"version_id": snapshot.version_id, "revision": snapshot.revision}))
            else:
                policy = ValidationPolicy.model_validate(
                    {"today": args.today, "earliest_signing_date": args.earliest_date}
                )
                form = CRSFormData.model_validate(read_object(args.file))
                result = await ValidationEngine(loader).validate(form, policy)
                print(result.model_dump_json())
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
