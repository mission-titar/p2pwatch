"""Catalog 0012 renames three columns and nothing else (descriptive names spec, D5)."""

import re
import sqlite3
from importlib import resources
from pathlib import Path

from p2pwatch.adapters.driven.persistence_sqlite.connection import open_catalog
from p2pwatch_testing.adapters.persistence_sqlite.older_catalog import (
    insert_v11_observation,
    insert_v11_source_point,
    open_catalog_at,
)
from p2pwatch_testing.catalog_rows import insert_decision, insert_file, insert_source

_A, _USER = "a" * 32, "1f2e" * 8
_RENAMED = {
    ("source_observations", "transfer_counter", "session_received_bytes"),
    ("source_variants", "directly_reachable", "connectable"),
    ("observation_variants", "media_length_sec", "duration_seconds"),
}
_RENAME = re.compile(r"ALTER TABLE (\w+) RENAME COLUMN (\w+) TO (\w+)")


def _schema(connection: sqlite3.Connection) -> list[tuple[str, str, str | None]]:
    return connection.execute(
        "SELECT type, name, sql FROM sqlite_schema ORDER BY type, name"
    ).fetchall()


def _rows(connection: sqlite3.Connection) -> dict[str, list[tuple[object, ...]]]:
    tables = [name for kind, name, _ in _schema(connection) if kind == "table"]
    return {
        table: connection.execute(f"SELECT * FROM {table} ORDER BY 1, 2").fetchall()
        for table in tables
    }


def _renamed(sql: str | None) -> str | None:
    for _, old, new in _RENAMED:
        sql = None if sql is None else re.sub(rf"\b{old}\b", new, sql)
    return sql


def test_0012_renames_the_three_columns_in_the_schema_and_keeps_every_value(
    tmp_path: Path,
) -> None:
    path = tmp_path / "catalog.db"
    connection = open_catalog_at(path, 11)
    insert_file(connection, _A)
    insert_v11_observation(connection, _A, "Keroro 062.avi", media_length_sec=1474)
    insert_decision(connection, _A, "062A", "download")
    insert_source(connection, _USER)
    insert_v11_source_point(connection, _A, _USER, directly_reachable=True, transfer_counter=7)
    schema, rows = _schema(connection), _rows(connection)
    connection.close()

    connection = open_catalog(path)
    try:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 12
        assert _schema(connection) == [(kind, name, _renamed(sql)) for kind, name, sql in schema]
        assert _rows(connection) == rows
        assert all(rows[table] for table, _, _ in _RENAMED)
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    finally:
        connection.close()


def test_0012_holds_only_the_three_column_renames() -> None:
    catalog = (
        resources.files("p2pwatch.adapters.driven.persistence_sqlite") / "migrations" / "catalog"
    )
    (script,) = [entry for entry in catalog.iterdir() if entry.name.startswith("0012_")]
    code = "\n".join(
        line
        for line in script.read_text(encoding="utf-8").splitlines()
        if not line.startswith("--")
    )
    statements = [" ".join(part.split()) for part in code.split(";") if part.strip()]
    renames = [_RENAME.fullmatch(statement) for statement in statements]
    assert None not in renames
    assert {match.groups() for match in renames if match is not None} == _RENAMED
