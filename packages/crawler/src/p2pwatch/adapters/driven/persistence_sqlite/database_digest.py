"""A digest of a database's content, to tell whether a pre-migration copy still matches it."""

import sqlite3
from hashlib import sha256

_MODULUS = 1 << 256


def database_digest(connection: sqlite3.Connection) -> bytes:
    """Covers the ``user_version``, the schema and every row of every table ``sqlite_schema``
    lists, SQLite's own included, whatever the rows' order, read through SQLite."""
    user_version = connection.execute("PRAGMA user_version").fetchone()[0]
    schema = connection.execute("SELECT sql FROM sqlite_schema ORDER BY sql").fetchall()
    table_names = connection.execute(
        "SELECT name FROM sqlite_schema WHERE type = 'table' ORDER BY name"
    ).fetchall()
    rows_sum = 0
    for (table_name,) in table_names:
        quoted = '"' + table_name.replace('"', '""') + '"'
        for row in connection.execute(f"SELECT * FROM {quoted}"):
            # Added, so the rows' order does not matter; repr keeps 1, '1' and b'1' apart.
            row_hash = sha256(repr((table_name, row)).encode()).digest()
            rows_sum = (rows_sum + int.from_bytes(row_hash)) % _MODULUS
    return sha256(repr((user_version, schema, rows_sum)).encode()).digest()
