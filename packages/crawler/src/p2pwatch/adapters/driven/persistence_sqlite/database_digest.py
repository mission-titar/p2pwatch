"""A digest of a database's content, to tell whether a pre-migration copy still matches it."""

import sqlite3
from hashlib import sha256

from p2pwatch.adapters.driven.persistence_sqlite.named_row import named_row

_MODULUS = 1 << 256


def database_digest(connection: sqlite3.Connection) -> bytes:
    """Covers the ``user_version`` and every line of ``iterdump``, whatever their order: the schema,
    every row, ``sqlite_sequence`` and ``sqlite_stat1``, not the other ``sqlite_stat*``."""
    # A cursor of its own: raw connections are digested too, the copier's candidate among them.
    cursor = connection.cursor()
    cursor.row_factory = named_row
    user_version = cursor.execute("PRAGMA user_version").fetchone()["user_version"]
    lines_sum = 0
    for line in connection.iterdump():
        # Added, so the rows' order does not matter.
        lines_sum = (lines_sum + int.from_bytes(sha256(line.encode()).digest())) % _MODULUS
    return sha256(repr((user_version, lines_sum)).encode()).digest()
