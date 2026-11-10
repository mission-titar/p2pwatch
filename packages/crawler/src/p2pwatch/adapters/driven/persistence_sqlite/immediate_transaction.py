"""``immediate_transaction``: the stores' write transaction on a connection in autocommit."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager, suppress


@contextmanager
def immediate_transaction(connection: sqlite3.Connection) -> Iterator[None]:
    """Runs the block in a ``BEGIN IMMEDIATE`` transaction, committed when it ends, rolled back
    when anything raises, which propagates."""
    # Outside the try: a failed BEGIN rolls back no transaction its caller had open.
    connection.execute("BEGIN IMMEDIATE")
    try:
        yield
        # Inside the try: a failed COMMIT leaves the transaction open, so it is rolled back too.
        connection.execute("COMMIT")
    except BaseException:
        # SQLite rolls a full disk back itself: this ROLLBACK then fails, never hiding the cause.
        with suppress(sqlite3.Error):
            connection.execute("ROLLBACK")
        raise
