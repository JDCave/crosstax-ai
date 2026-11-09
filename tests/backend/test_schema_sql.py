"""Prevent stale hand-written DDL from diverging from current models or migrations."""

import re
import subprocess
import sys

from backend.cli.schema_sql import BASE_TABLES, ROOT, SQL_DIRECTORY, render_sql_files, rule_tables
from backend.models.user import User  # noqa: F401 — unrelated metadata must not leak into rule DDL.


def table_names(sql):
    return re.findall(r"CREATE TABLE crosstax\.(\w+)", sql)


def test_all_sql_artifacts_are_current_and_transactional():
    generated = render_sql_files()
    assert {path.name for path in SQL_DIRECTORY.glob("*.sql")} == set(generated)
    for filename, content in generated.items():
        assert (SQL_DIRECTORY / filename).read_text(encoding="utf-8") == content
        assert content.count("BEGIN;") == 1 and content.count("COMMIT;") == 1
        assert "DROP " not in content and "TRUNCATE " not in content
        assert not any(line != line.rstrip() for line in content.splitlines())


def test_full_snapshot_includes_all_rules_and_excludes_scaffold():
    sql = render_sql_files()["validation_engine.sql"]
    assert set(table_names(sql)) == {table.name for table in rule_tables()}
    assert len(table_names(sql)) == 11
    assert "users" not in sql and "alembic_version" not in sql
    assert "INSERT INTO crosstax.rule_engine_state (id) VALUES (1);" in sql
    assert "INSERT INTO crosstax.rule_task_queue_state (id, generation) VALUES (1, 0);" in sql
    assert "CREATE SCHEMA IF NOT EXISTS crosstax;" in sql
    assert "payload_ciphertext TEXT" in sql and "result_ciphertext TEXT" in sql
    for table in rule_tables():
        for column in table.columns:
            assert re.search(rf"\b{column.name}\b", sql)
        for index in table.indexes:
            assert f"CREATE INDEX {index.name} " in sql


def test_bootstrap_is_only_the_prerequisite_baseline():
    sql = render_sql_files()["bootstrap_rules.sql"]
    assert set(table_names(sql)) == BASE_TABLES
    assert "rule_validation_tasks" not in sql and "rule_publications" not in sql
    assert "INSERT INTO crosstax.rule_engine_state (id) VALUES (1);" in sql


def test_task_incremental_remains_identical_to_migration_rendering():
    files = render_sql_files()
    sql = files["rule_validation_tasks.sql"]
    assert set(table_names(sql)) == {"rule_validation_tasks", "rule_task_queue_state"}
    assert "FOREIGN KEY(rule_version_id) REFERENCES crosstax.rule_versions" in sql
    full = files["validation_engine.sql"]
    for name in ("ix_rule_task_claim", "ix_rule_task_expiry", "ix_rule_task_session"):
        assert re.search(rf"CREATE INDEX {name} .*?;", sql).group() in full


def test_sql_check_cli_needs_no_running_database():
    result = subprocess.run([sys.executable, "-m", "backend.cli.schema_sql", "--check"],
                            cwd=ROOT, capture_output=True, text=True, check=True)
    assert "matches ORM" in result.stdout
