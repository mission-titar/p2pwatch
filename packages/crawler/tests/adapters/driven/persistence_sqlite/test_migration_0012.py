"""Catalog 0012 renames three columns and nothing else (descriptive names spec, D5)."""

import re
import sqlite3
from importlib import resources
from pathlib import Path
from typing import Any

from tests.support.adapters.driven.persistence_sqlite.named_row import rows
from tests.support.adapters.driven.persistence_sqlite.older_catalog import (
    insert_v11_observation,
    insert_v11_source_point,
    insert_v14_decision,
    open_catalog_at,
)
from tests.support.catalog_rows import insert_file, insert_source

_A, _USER = "a" * 32, "1f2e" * 8
_RENAMED = {
    ("source_observations", "transfer_counter", "session_received_bytes"),
    ("source_variants", "directly_reachable", "connectable"),
    ("observation_variants", "media_length_sec", "duration_seconds"),
}
_RENAME = re.compile(r"ALTER TABLE (\w+) RENAME COLUMN (\w+) TO (\w+)")


def _schema(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    return rows(connection, sql="SELECT type, name, sql FROM sqlite_schema ORDER BY type, name")


def _table_rows(connection: sqlite3.Connection) -> dict[str, list[dict[str, Any]]]:
    tables = [row["name"] for row in _schema(connection) if row["type"] == "table"]
    return {table: rows(connection, sql=f"SELECT * FROM {table} ORDER BY 1, 2") for table in tables}


def _renamed_columns(row: dict[str, Any]) -> dict[str, Any]:
    new_name_by_old = {old: new for _, old, new in _RENAMED}
    return {new_name_by_old.get(name, name): value for name, value in row.items()}


def _renamed(sql: str | None) -> str | None:
    for _, old, new in _RENAMED:
        sql = None if sql is None else re.sub(rf"\b{old}\b", new, sql)
    return sql


def test_0012_renames_the_three_columns_in_the_schema_and_keeps_every_value(
    tmp_path: Path,
) -> None:
    path = tmp_path / "catalog.db"
    connection = open_catalog_at(path, version=11)
    insert_file(connection, native_id=_A)
    insert_v11_observation(
        connection, native_id=_A, filename="Keroro 062.avi", media_length_sec=1474
    )
    insert_v14_decision(connection, native_id=_A)
    insert_source(connection, user_hash=_USER)
    insert_v11_source_point(
        connection, native_id=_A, user_hash=_USER, directly_reachable=True, transfer_counter=7
    )
    schema, table_rows = _schema(connection), _table_rows(connection)
    connection.close()

    connection = open_catalog_at(path, version=12)
    try:
        assert rows(connection, sql="PRAGMA user_version") == [{"user_version": 12}]
        assert _schema(connection) == [{**row, "sql": _renamed(row["sql"])} for row in schema]
        assert _table_rows(connection) == {
            table: [_renamed_columns(row) for row in kept] for table, kept in table_rows.items()
        }
        assert all(table_rows[table] for table, _, _ in _RENAMED)
        assert rows(connection, sql="PRAGMA integrity_check") == [{"integrity_check": "ok"}]
    finally:
        connection.close()


def test_0012_holds_only_the_three_column_renames() -> None:
    catalog = (
        resources.files("p2pwatch.adapters.driven.persistence_sqlite") / "migrations" / "catalog"
    )
    (script,) = [
        script_file for script_file in catalog.iterdir() if script_file.name.startswith("0012_")
    ]
    code = "\n".join(
        line
        for line in script.read_text(encoding="utf-8").splitlines()
        if not line.startswith("--")
    )
    statements = [" ".join(part.split()) for part in code.split(";") if part.strip()]
    renames = [_RENAME.fullmatch(statement) for statement in statements]
    assert None not in renames
    assert {match.groups() for match in renames if match is not None} == _RENAMED
