"""Offline rule impact analysis; scheduled update commands added separately."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

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
    args = parser.parse_args()
    try:
        impact_command(args)
    except (ValueError, OSError) as exc:
        print(json.dumps({"status": "FAILED", "error_type": type(exc).__name__}))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
