"""Local 0013 renames ``backoff_states.started_at`` to ``started_at_micros`` (micros spec, D1)."""

import re
import sqlite3
from importlib import resources
from pathlib import Path
from typing import Any

from tests.support.adapters.driven.persistence_sqlite.named_row import rows
from tests.support.adapters.driven.persistence_sqlite.older_catalog import open_local_at

_RENAME = re.compile(r"ALTER TABLE (\w+) RENAME COLUMN (\w+) TO (\w+)")


def _schema(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    return rows(connection, sql="SELECT type, name, sql FROM sqlite_schema ORDER BY type, name")


def _renamed(sql: str | None) -> str | None:
    return None if sql is None else re.sub(r"\bstarted_at\b", "started_at_micros", sql)


def test_0013_renames_started_at_in_the_schema_and_keeps_every_value(tmp_path: Path) -> None:
    path = tmp_path / "local.db"
    connection = open_local_at(path, version=12)
    connection.execute(
        "INSERT INTO backoff_states VALUES ('amule-1', 'kad', 2, 1781258400123456, 300.0)"
    )
    schema = _schema(connection)
    backoff_states = rows(connection, sql="SELECT * FROM backoff_states")
    connection.close()

    connection = open_local_at(path, version=13)
    try:
        assert rows(connection, sql="PRAGMA user_version") == [{"user_version": 13}]
        assert _schema(connection) == [{**row, "sql": _renamed(row["sql"])} for row in schema]
        assert rows(connection, sql="SELECT * FROM backoff_states") == [
            {
                "started_at_micros" if name == "started_at" else name: value
                for name, value in backoff_state.items()
            }
            for backoff_state in backoff_states
        ]
        assert rows(connection, sql="SELECT started_at_micros FROM backoff_states") == [
            {"started_at_micros": 1_781_258_400_123_456}
        ]
        assert (
            rows(
                connection,
                sql="SELECT m.name AS table_name FROM sqlite_schema AS m,"
                " pragma_table_xinfo(m.name) AS c"
                " WHERE m.type = 'table' AND c.name = 'started_at'",
            )
            == []
        )
    finally:
        connection.close()


def test_0013_holds_only_the_column_rename() -> None:
    local = resources.files("p2pwatch.adapters.driven.persistence_sqlite") / "migrations" / "local"
    (script,) = [
        script_file for script_file in local.iterdir() if script_file.name.startswith("0013_")
    ]
    code = "\n".join(
        line
        for line in script.read_text(encoding="utf-8").splitlines()
        if not line.startswith("--")
    )
    statements = [" ".join(part.split()) for part in code.split(";") if part.strip()]
    renames = [_RENAME.fullmatch(statement) for statement in statements]
    assert None not in renames
    assert {match.groups() for match in renames if match is not None} == {
        ("backoff_states", "started_at", "started_at_micros")
    }
