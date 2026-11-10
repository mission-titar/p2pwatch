"""A SQLite database refusing every write, full or read-only, for the stores' contracts."""

import sqlite3
from enum import StrEnum

from tests.support.refused_writes import RefuseWrites


class StorageRefusal(StrEnum):
    FULL = "full"
    READ_ONLY = "read-only"


_PRAGMA_BY_REFUSAL = {
    # Never set below the database's own size: no page left for a write needing one.
    StorageRefusal.FULL: "PRAGMA max_page_count = 1",
    StorageRefusal.READ_ONLY: "PRAGMA query_only = ON",
}


def refusing(connection: sqlite3.Connection, *, refusal: StorageRefusal) -> RefuseWrites:
    """What makes ``connection``'s database refuse every write as ``refusal`` says."""

    def refuse_writes() -> None:
        connection.execute(_PRAGMA_BY_REFUSAL[refusal])

    return refuse_writes
