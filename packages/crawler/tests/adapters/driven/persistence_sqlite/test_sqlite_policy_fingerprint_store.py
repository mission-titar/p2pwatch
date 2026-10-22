import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from p2pwatch.adapters.driven.persistence_sqlite.connection import open_local
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_policy_fingerprint_store import (
    SqlitePolicyFingerprintStore,
)


@pytest.fixture
def connection(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    local = open_local(tmp_path / "local.db")
    yield local
    local.close()


@pytest.fixture
def policy_fingerprint_store(connection: sqlite3.Connection) -> SqlitePolicyFingerprintStore:
    return SqlitePolicyFingerprintStore(connection)


def test_no_policy_fingerprint_is_read_before_one_is_set(
    policy_fingerprint_store: SqlitePolicyFingerprintStore,
) -> None:
    assert policy_fingerprint_store.read_policy_fingerprint() is None


def test_a_set_policy_fingerprint_is_read_back(
    policy_fingerprint_store: SqlitePolicyFingerprintStore,
) -> None:
    policy_fingerprint_store.set_policy_fingerprint("abc")
    assert policy_fingerprint_store.read_policy_fingerprint() == "abc"


def test_a_second_policy_fingerprint_replaces_the_first(
    policy_fingerprint_store: SqlitePolicyFingerprintStore,
) -> None:
    policy_fingerprint_store.set_policy_fingerprint("abc")
    policy_fingerprint_store.set_policy_fingerprint("def")
    assert policy_fingerprint_store.read_policy_fingerprint() == "def"
