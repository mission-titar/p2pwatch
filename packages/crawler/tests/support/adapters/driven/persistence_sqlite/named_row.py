"""The tests' reads of a row, by column name whatever factory the connection carries."""

import sqlite3
from collections.abc import Sequence
from typing import Any

from p2pwatch.adapters.driven.persistence_sqlite.named_row import named_row


def rows(
    connection: sqlite3.Connection, sql: str, parameters: Sequence[object] = ()
) -> list[dict[str, Any]]:
    """Plain dicts, since pytest's diff of a failing comparison iterates a ``NamedRow``."""
    cursor = connection.cursor()
    cursor.row_factory = named_row
    return [dict(row) for row in cursor.execute(sql, parameters)]
