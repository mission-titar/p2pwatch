"""Local 0012 renames the downloads' two ``last_*`` columns and nothing else (lot B's spec, D7)."""

import re
import sqlite3
from importlib import resources
from pathlib import Path

from p2pwatch.domain.file_key import FileKey, Network
from tests.support.adapters.driven.persistence_sqlite.older_catalog import open_local_at
from tests.support.adapters.driven.persistence_sqlite.sqlite_database_opener import open_local

_A = FileKey(Network.ED2K, "a" * 32)
_RENAMED = {
    ("downloads", "last_seen_at", "latest_seen_at"),
    ("downloads", "last_progress_at", "latest_progress_at"),
}
_RENAME = re.compile(r"ALTER TABLE (\w+) RENAME COLUMN (\w+) TO (\w+)")


def _schema(connection: sqlite3.Connection) -> list[tuple[str, str, str | None]]:
    return connection.execute(
        "SELECT type, name, sql FROM sqlite_schema ORDER BY type, name"
    ).fetchall()


def _renamed(sql: str | None) -> str | None:
    for _, old, new in _RENAMED:
        sql = None if sql is None else re.sub(rf"\b{old}\b", new, sql)
    return sql


def test_0012_renames_the_two_columns_in_the_schema_and_keeps_every_value(
    tmp_path: Path,
) -> None:
    path = tmp_path / "local.db"
    connection = open_local_at(path, 11)
    connection.execute(
        "INSERT INTO downloads (file_id, network, native_id, target_id, state, queued_at,"
        " last_seen_at, bytes_done, last_progress_at)"
        " VALUES (?, 'ed2k', ?, '062A', 'downloading', '2026-10-01', '2026-10-02', 7,"
        " '2026-10-03')",
        (_A.file_id, _A.native_id),
    )
    schema = _schema(connection)
    rows = connection.execute("SELECT * FROM downloads").fetchall()
    connection.close()

    connection = open_local(path)
    try:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 12
        assert _schema(connection) == [(kind, name, _renamed(sql)) for kind, name, sql in schema]
        assert connection.execute("SELECT * FROM downloads").fetchall() == rows
        assert connection.execute(
            "SELECT latest_seen_at, latest_progress_at FROM downloads"
        ).fetchone() == ("2026-10-02", "2026-10-03")
    finally:
        connection.close()


def test_0012_holds_only_the_two_column_renames() -> None:
    local = resources.files("p2pwatch.adapters.driven.persistence_sqlite") / "migrations" / "local"
    (script,) = [
        script_file for script_file in local.iterdir() if script_file.name.startswith("0012_")
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
