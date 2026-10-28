"""Catalog 0014 renames both ``observed_at`` columns to ``observed_at_micros`` (micros spec, D1)."""

import re
import sqlite3
from importlib import resources
from pathlib import Path

from tests.support.adapters.driven.persistence_sqlite.older_catalog import (
    insert_v13_observation,
    insert_v13_source_point,
    insert_v14_decision,
    open_catalog_at,
)
from tests.support.catalog_rows import (
    insert_file,
    insert_source,
    insert_source_variant,
)

_A, _USER = "a" * 32, "1f2e" * 8
_RENAMED = {
    ("observations", "observed_at", "observed_at_micros"),
    ("source_observations", "observed_at", "observed_at_micros"),
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
    return None if sql is None else re.sub(r"\bobserved_at\b", "observed_at_micros", sql)


def test_0014_renames_observed_at_in_the_schema_and_keeps_every_value(tmp_path: Path) -> None:
    path = tmp_path / "catalog.db"
    connection = open_catalog_at(path, 13)
    insert_file(connection, _A)
    insert_v13_observation(connection, _A, "Keroro 062.avi")
    insert_v14_decision(connection, _A)
    insert_source(connection, _USER)
    insert_v13_source_point(connection, insert_source_variant(connection, _A, _USER))
    schema, rows = _schema(connection), _rows(connection)
    connection.close()

    connection = open_catalog_at(path, 14)
    try:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 14
        assert _schema(connection) == [(kind, name, _renamed(sql)) for kind, name, sql in schema]
        assert _rows(connection) == rows
        assert all(rows[table] for table, _, _ in _RENAMED)
        assert connection.execute(
            "SELECT o.observed_at_micros, p.observed_at_micros"
            " FROM observations AS o, source_observations AS p"
        ).fetchall() == [(1_781_258_400_123_456, 1_781_258_400_654_321)]
        assert (
            connection.execute(
                "SELECT m.name, c.name FROM sqlite_schema AS m, pragma_table_xinfo(m.name) AS c"
                " WHERE m.type = 'table' AND c.name = 'observed_at'"
            ).fetchall()
            == []
        )
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    finally:
        connection.close()


def test_0014_holds_only_the_two_column_renames() -> None:
    catalog = (
        resources.files("p2pwatch.adapters.driven.persistence_sqlite") / "migrations" / "catalog"
    )
    (script,) = [
        script_file for script_file in catalog.iterdir() if script_file.name.startswith("0014_")
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
