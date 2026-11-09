import sqlite3

import pytest

from p2pwatch.adapters.driven.persistence_sqlite.errors import (
    MigrationError,
    PersistenceError,
    wrap_sqlite_errors,
    wrap_stored_value_errors,
)
from p2pwatch.domain.store_error import StoreError


def test_persistence_error_satisfies_store_error_contract() -> None:
    assert issubclass(PersistenceError, StoreError)
    assert issubclass(MigrationError, StoreError)  # transitive via PersistenceError


def test_a_sqlite_error_comes_out_as_a_persistence_error_chained_to_it() -> None:
    cause = sqlite3.OperationalError("database is locked")
    with (
        pytest.raises(PersistenceError, match="^database is locked$") as raised,
        wrap_sqlite_errors(),
    ):
        raise cause
    assert raised.value.__cause__ is cause


@pytest.mark.parametrize(
    "cause", [ValueError("'bogus' is not a valid DownloadState"), OverflowError("out of range")]
)
def test_a_stored_value_that_cannot_be_read_back_is_a_persistence_error_chained_to_it(
    cause: Exception,
) -> None:
    with (
        pytest.raises(
            PersistenceError, match=f"^a stored value cannot be read: {cause}$"
        ) as raised,
        wrap_stored_value_errors(),
    ):
        raise cause
    assert raised.value.__cause__ is cause


def test_an_error_of_another_family_is_left_unwrapped() -> None:
    with pytest.raises(TypeError), wrap_stored_value_errors():
        raise TypeError("a bug")
