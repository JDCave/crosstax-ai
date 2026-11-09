"""Cron process locking, safe output and CLI boundaries."""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from backend.cli.rule_updates import main, read_json, write_report
from backend.infrastructure.job_lock import job_lock


def test_lock_excludes_other_processes_and_is_reusable(tmp_path):
    path = tmp_path / "update.lock"
    script = (
        "from pathlib import Path; from backend.infrastructure.job_lock import job_lock\n"
        f"with job_lock(Path({str(path)!r})) as acquired: print(acquired)"
    )
    with job_lock(path) as acquired:
        assert acquired
        result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, check=True)
        assert result.stdout.strip() == "False"
    with job_lock(path) as acquired:
        assert acquired
    assert path.exists()  # Unlinking during concurrent use would invalidate the lock guarantee.


def test_lock_refuses_symlinks(tmp_path):
    target = tmp_path / "target"
    target.write_text("keep", encoding="utf-8")
    link = tmp_path / "link"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlink creation requires privileges on this platform")
    with pytest.raises(OSError), job_lock(link):
        pass
    assert target.read_text(encoding="utf-8") == "keep"


def test_report_replace_is_atomic_and_cleans_temporary_files(tmp_path):
    report = tmp_path / "report.json"
    write_report(report, {"status": "OLD"})
    with (
        patch("backend.cli.rule_updates.os.replace", side_effect=PermissionError("PRIVATE PATH")),
        pytest.raises(PermissionError),
    ):
        write_report(report, {"status": "NEW"})
    assert json.loads(report.read_text(encoding="utf-8")) == {"status": "OLD"}
    assert not list(tmp_path.glob(".rule-update-*"))
    write_report(report, {"status": "NEW"})
    assert json.loads(report.read_text(encoding="utf-8")) == {"status": "NEW"}


def test_locked_cli_skips_without_reading_inputs_or_overwriting_report(tmp_path, monkeypatch, capsys):
    lock = tmp_path / "run.lock"
    report = tmp_path / "report.json"
    report.write_text('{"status":"PREVIOUS"}', encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["rule_updates", "run", "--lock-file", str(lock), "--output", str(report)])
    with job_lock(lock), patch("backend.cli.rule_updates.run_command", new_callable=AsyncMock) as execute:
        main()
    execute.assert_not_awaited()
    assert json.loads(capsys.readouterr().out)["status"] == "SKIPPED_LOCKED"
    assert json.loads(report.read_text(encoding="utf-8"))["status"] == "PREVIOUS"


def test_publication_requires_independent_policy_and_output_cannot_overwrite_inputs(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["rule_updates", "run", "--publish"])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    case = tmp_path / "cases.json"
    case.write_text("[]", encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["rule_updates", "run", "--cases", str(case), "--output", str(case)])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 1
    assert json.loads(capsys.readouterr().out)["error_type"] == "ValueError"
    assert case.read_text(encoding="utf-8") == "[]"


def test_input_limit_and_empty_policy_are_safe(tmp_path):
    from backend.services.rule_updates import PublicationPolicy

    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b" " * 1048577)
    with pytest.raises(ValueError):
        read_json(oversized)
    policy = PublicationPolicy.model_validate_json(
        Path("backend/engine/scheduling/publication-policy.example.json").read_text(encoding="utf-8"),
    )
    assert policy.approvals == []


def test_upstream_schema_snapshots_match_models():
    from backend.services.rule_updates import PublicationPolicy, RuleBundle

    for model, name in ((RuleBundle, "rule-bundle.schema.json"), (PublicationPolicy, "publication-policy.schema.json")):
        assert json.loads(Path("backend/engine", name).read_text(encoding="utf-8")) == model.model_json_schema()
