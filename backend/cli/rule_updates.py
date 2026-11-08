"""Offline impact analysis and single-host scheduled rule updates."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from backend.engine.contracts import ValidationPolicy
from backend.engine.impact import analyze_impact
from backend.engine.reproducibility import canonical_hash
from backend.engine.rule_loader import RuleLoader, compile_snapshot
from backend.engine.validation import ValidationEngine


def read_json(path: Path) -> object:
    with path.open("rb") as stream:
        raw = stream.read(1_048_577)
    if len(raw) > 1_048_576:
        raise ValueError("JSON input exceeds 1 MiB")
    return json.loads(raw)


def impact_command(args: argparse.Namespace) -> None:
    from typing import cast

    from backend.infrastructure.database import async_session_factory

    versions = []
    for path, revision in ((args.base, args.base_revision), (args.candidate, args.base_revision + 1)):
        rules = read_json(path)
        if not isinstance(rules, dict):
            raise ValueError("Expected a rule object")
        versions.append(compile_snapshot(canonical_hash(rules), revision, cast(dict[str, object], rules)))
    engine = ValidationEngine(RuleLoader(async_session_factory))
    policy = ValidationPolicy.model_validate({"today": args.today, "earliest_signing_date": args.earliest_date})
    report = analyze_impact(engine, versions[0], versions[1], read_json(args.cases), policy)
    print(report.model_dump_json(indent=2))


def write_report(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=".rule-update-", delete=False
        ) as stream:
            temporary = Path(stream.name)
            json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


async def run_command(args: argparse.Namespace) -> int:
    import httpx

    from backend.infrastructure.database import async_session_factory, engine
    from backend.services.rule_import import RuleSourceImporter
    from backend.services.rule_updates import PublicationPolicy, RuleBundle, RuleUpdateCoordinator

    try:
        bundle = RuleBundle.model_validate(read_json(args.bundle)) if args.bundle and args.bundle.exists() else None
        trusted = PublicationPolicy.model_validate(read_json(args.policy)) if args.policy else None
        today = args.today or datetime.now(UTC).astimezone(ZoneInfo(args.timezone)).date().isoformat()
        policy = ValidationPolicy.model_validate({"today": today, "earliest_signing_date": args.earliest_date})
        cases = read_json(args.cases)
        async with httpx.AsyncClient(headers={"User-Agent": "CrossTaxAI-RuleSync/0.1"}) as client:
            job = RuleUpdateCoordinator(async_session_factory, RuleSourceImporter(async_session_factory, client))
            result = await job.run(
                bundle,
                cases,
                policy,
                publication_policy=trusted,
                publish=args.publish,
                sync_sources=not args.skip_source_sync,
                trigger_type="SCHEDULED" if args.scheduled else "MANUAL",
            )
        data = result.model_dump(mode="json")
        if args.output:
            try:
                write_report(args.output, data)
            except OSError as exc:
                # Activation may already be committed: retain its actual decision in stdout.
                data["output_error"] = type(exc).__name__
                print(json.dumps(data, ensure_ascii=False, indent=2))
                return 1
        print(json.dumps(data, ensure_ascii=False, indent=2))
        if result.status in {"FAILED", "CONFLICT", "BLOCKED", "NO_ACTIVE_RULES"}:
            return 1
        return 2 if result.status in {"PENDING_APPROVAL", "WAITING_FOR_BUNDLE"} else 0
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Rule impact and background updates")
    commands = parser.add_subparsers(dest="command", required=True)
    impact = commands.add_parser("impact", help="Compare full rule snapshots without DB calls or AI")
    impact.add_argument("--base", type=Path, required=True)
    impact.add_argument("--candidate", type=Path, required=True)
    impact.add_argument("--cases", type=Path, default=Path("assets/mock-data/cases.json"))
    impact.add_argument("--today", required=True)
    impact.add_argument("--earliest-date")
    impact.add_argument("--base-revision", type=int, default=0)
    run = commands.add_parser("run", help="Check sources and upstream bundles; publication is explicitly opt-in")
    run.add_argument("--bundle", type=Path, help="Upstream full structured bundle; a missing file means waiting")
    run.add_argument("--policy", type=Path, help="Maintainer-controlled exact publication approvals")
    run.add_argument("--publish", action="store_true")
    run.add_argument("--skip-source-sync", action="store_true", help="Use already imported documents")
    run.add_argument("--scheduled", action="store_true")
    run.add_argument("--cases", type=Path, default=Path("assets/mock-data/cases.json"))
    run.add_argument("--today", help="Explicit evaluation date, overrides the business timezone clock")
    run.add_argument("--timezone", default="Asia/Shanghai")
    run.add_argument("--earliest-date")
    run.add_argument("--lock-file", type=Path, default=Path("outputs/rule-updates.lock"))
    run.add_argument("--output", type=Path, help="Atomically replace a JSON report after a completed job")
    args = parser.parse_args()
    if args.command == "run" and args.publish and not args.policy:
        parser.error("--publish requires an independent --policy file")
    try:
        if args.command == "impact":
            impact_command(args)
            return
        if args.output and args.output.resolve() in {
            path.resolve() for path in (args.bundle, args.policy, args.cases, args.lock_file) if path is not None
        }:
            raise ValueError("Output must not overwrite job inputs or its lock")
        from backend.infrastructure.job_lock import job_lock

        with job_lock(args.lock_file) as acquired:
            if not acquired:
                print(json.dumps({"status": "SKIPPED_LOCKED"}))
                return
            raise SystemExit(asyncio.run(run_command(args)))
    except Exception as exc:
        print(json.dumps({"status": "FAILED", "error_type": type(exc).__name__}))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
