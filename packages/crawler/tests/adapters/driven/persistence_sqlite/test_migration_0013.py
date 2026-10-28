"""Catalog 0013 renames ``raw_meta`` to ``raw_metadata`` and nothing else (lot B's spec, D7)."""

import re
import sqlite3
from importlib import resources
from pathlib import Path

from tests.support.adapters.driven.persistence_sqlite.older_catalog import (
    insert_v12_observation,
    insert_v12_source_point,
    insert_v14_decision,
    open_catalog_at,
)
from tests.support.catalog_rows import insert_file, insert_source

_A, _USER = "a" * 32, "1f2e" * 8
_RENAMED = {
    ("observation_variants", "raw_meta", "raw_metadata"),
    ("source_variants", "raw_meta", "raw_metadata"),
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
    return None if sql is None else re.sub(r"\braw_meta\b", "raw_metadata", sql)


def test_0013_renames_raw_meta_in_the_schema_and_keeps_every_value(tmp_path: Path) -> None:
    path = tmp_path / "catalog.db"
    connection = open_catalog_at(path, 12)
    insert_file(connection, _A)
    insert_v12_observation(connection, _A, "Keroro 062.avi")
    insert_v14_decision(connection, _A)
    insert_source(connection, _USER)
    insert_v12_source_point(connection, _A, _USER)
    schema, rows = _schema(connection), _rows(connection)
    connection.close()

    connection = open_catalog_at(path, 13)
    try:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 13
        assert _schema(connection) == [(kind, name, _renamed(sql)) for kind, name, sql in schema]
        assert _rows(connection) == rows
        assert all(rows[table] for table, _, _ in _RENAMED)
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    finally:
        connection.close()


def test_0013_holds_only_the_two_column_renames() -> None:
    catalog = (
        resources.files("p2pwatch.adapters.driven.persistence_sqlite") / "migrations" / "catalog"
    )
    (script,) = [
        script_file for script_file in catalog.iterdir() if script_file.name.startswith("0013_")
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
