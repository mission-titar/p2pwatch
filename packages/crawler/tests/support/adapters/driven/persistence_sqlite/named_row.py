"""The tests' reads of a row, by column name whatever factory the connection carries."""

import sqlite3
from collections.abc import Sequence
from typing import Any


def rows(
    connection: sqlite3.Connection, sql: str, parameters: Sequence[object] = ()
) -> list[dict[str, Any]]:
    """Plain dicts, since pytest's diff of a failing comparison iterates a ``NamedRow``; a column
    name that appears twice is refused, as the opener refuses it."""
    cursor = connection.cursor()
    # Tuples: a cursor's factory overrides its connection's.
    cursor.row_factory = None
    cursor.execute(sql, parameters)
    names = [column[0] for column in cursor.description]
    for name in names:
        if names.count(name) > 1:
            raise ValueError(f"the column {name!r} appears twice")
    return [dict(zip(names, values, strict=True)) for values in cursor]
