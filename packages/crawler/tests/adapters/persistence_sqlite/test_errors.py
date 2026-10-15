import sqlite3

import pytest

from p2pwatch.adapters.persistence_sqlite.errors import (
    MigrationError,
    PersistenceError,
    wrap_sqlite_errors,
)
from p2pwatch.ports.repository_errors import RepositoryError


def test_persistence_error_satisfies_repository_error_contract() -> None:
    assert issubclass(PersistenceError, RepositoryError)
    assert issubclass(MigrationError, RepositoryError)  # transitive via PersistenceError


def test_a_sqlite_error_comes_out_as_a_persistence_error_chained_to_it() -> None:
    cause = sqlite3.OperationalError("database is locked")
    with (
        pytest.raises(PersistenceError, match="^database is locked$") as raised,
        wrap_sqlite_errors(),
    ):
        raise cause
    assert raised.value.__cause__ is cause
