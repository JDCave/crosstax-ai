"""Conservative ORM bootstrap plus the existing Alembic chain; no arbitrary SQL input."""

from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, MetaData, inspect
from sqlalchemy.schema import BLANK_SCHEMA, CreateSchema

from backend.models import Base

BASE_TABLES = frozenset(
    {
        "rule_sources",
        "rule_sync_runs",
        "rule_documents",
        "rule_versions",
        "rule_version_documents",
        "rule_engine_state",
    }
)
ROOT = Path(__file__).resolve().parents[2]


class SchemaConflict(ValueError):
    """Existing schema cannot safely be inferred or stamped."""


def schema_metadata(schema: str | None) -> MetaData:
    metadata = MetaData()
    for table in Base.metadata.sorted_tables:
        if table.schema == "crosstax" and table.name.startswith("rule_"):
            table.to_metadata(  # SQLAlchemy supports clearing/remapping schemas despite narrow annotations.
                metadata,
                schema=schema,  # type: ignore[arg-type]
                referred_schema_fn=lambda *args: schema if schema is not None else BLANK_SCHEMA,  # type: ignore[arg-type]
            )
    return metadata


def upgrade_rule_schema(connection: Connection) -> tuple[str, int]:
    sqlite = connection.dialect.name == "sqlite"
    if not sqlite and connection.dialect.name != "postgresql":
        raise SchemaConflict("Unsupported database backend")
    mapping = connection.get_execution_options().get("schema_translate_map") or {}
    schema = None if sqlite else mapping.get("crosstax", "crosstax")
    tracking_schema = schema if not sqlite and schema != "crosstax" else None
    inspector = inspect(connection)
    exists = sqlite or schema in inspector.get_schema_names()
    names = {name for name in inspector.get_table_names(schema=schema) if name.startswith("rule_")} if exists else set()
    metadata = schema_metadata(schema)
    expected = {table.name for table in metadata.tables.values()}
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    scripts = ScriptDirectory.from_config(config)
    heads = MigrationContext.configure(connection, opts={"version_table_schema": tracking_schema}).get_current_heads()
    inventories = {
        "20261103_rule_history": BASE_TABLES | {"rule_audit_records", "rule_publications"},
        "20261108_rule_tasks": BASE_TABLES
        | {"rule_audit_records", "rule_publications", "rule_validation_tasks", "rule_task_queue_state"},
        scripts.get_current_head(): expected,
    }
    if heads:
        if len(heads) != 1 or heads[0] not in inventories or names != inventories[heads[0]]:
            raise SchemaConflict("Migration state and rule tables disagree")
    elif names and names != BASE_TABLES:
        raise SchemaConflict("Only empty schemas or the complete legacy baseline can be bootstrapped")
    # Inspect existing columns before any DDL. Never silently treat incompatible tables as initialized.
    for name in names:
        table = metadata.tables[name if sqlite else f"{schema}.{name}"]
        columns = {column["name"]: column for column in inspector.get_columns(name, schema=schema)}
        if set(columns) != {column.name for column in table.columns}:
            raise SchemaConflict("Existing columns differ from ORM")
        for column in table.columns:
            current = columns[column.name]
            if str(current["type"].compile(dialect=connection.dialect)) != str(
                column.type.compile(dialect=connection.dialect)
            ):
                raise SchemaConflict("Existing column types differ from ORM")
            if current["nullable"] != column.nullable:
                raise SchemaConflict("Existing column nullability differs from ORM")
        if set(inspector.get_pk_constraint(name, schema=schema)["constrained_columns"]) != {
            c.name for c in table.primary_key
        }:
            raise SchemaConflict("Existing primary keys differ from ORM")
    if not exists:
        if not isinstance(schema, str):
            raise SchemaConflict("A PostgreSQL schema name is required")
        connection.execute(CreateSchema(schema, if_not_exists=True))
    if not heads:
        tables = [
            table for table in Base.metadata.sorted_tables if table.schema == "crosstax" and table.name in BASE_TABLES
        ]
        Base.metadata.create_all(connection, tables=tables, checkfirst=True)
    config.attributes["connection"] = connection
    config.attributes["version_table_schema"] = tracking_schema
    command.upgrade(config, "head")
    target_schema = schema
    context = MigrationContext.configure(
        connection,
        opts={
            "include_schemas": not sqlite,
            "compare_type": True,
            "compare_server_default": True,
            "include_name": lambda name, kind, parents: name == target_schema if kind == "schema" else True,
            "include_object": lambda obj, name, kind, reflected, compare_to: (
                name in expected if kind == "table" else True
            ),
        },
    )
    if compare_metadata(context, metadata):
        raise SchemaConflict("Schema still differs from ORM after migration")
    head = scripts.get_current_head()
    assert head is not None
    return head, len(expected)
