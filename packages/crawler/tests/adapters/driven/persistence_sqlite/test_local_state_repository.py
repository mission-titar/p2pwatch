import sqlite3
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from p2pwatch.adapters.driven.persistence_sqlite.connection import open_local
from p2pwatch.adapters.driven.persistence_sqlite.errors import PersistenceError
from p2pwatch.adapters.driven.persistence_sqlite.local_state_repository import (
    SqliteLocalStateRepository,
)
from p2pwatch.ports.driven.local_state_repository import LocalStateRepository

_START = datetime(2026, 6, 11, 12, 0, 0, tzinfo=UTC)
_NODE_ID_QUERY = "SELECT value FROM node_runtime WHERE key = 'node_id'"


@pytest.fixture
def connection(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    local = open_local(tmp_path / "local.db")
    yield local
    local.close()


@pytest.fixture
def repository(connection: sqlite3.Connection) -> SqliteLocalStateRepository:
    return SqliteLocalStateRepository(connection)


# --- node_id (spec §3) ---------------------------------------------------------------


def test_node_id_is_created_on_first_call_and_stable(
    repository: SqliteLocalStateRepository, connection: sqlite3.Connection
) -> None:
    created = repository.get_or_create_node_id(_START)
    assert uuid.UUID(created)  # a REAL UUID, verifiable
    later = _START + timedelta(days=1)
    assert repository.get_or_create_node_id(later) == created  # stable on the second call
    fresh = SqliteLocalStateRepository(connection)  # and any future instance
    assert fresh.get_or_create_node_id(later) == created


def test_node_id_persists_created_at_alongside(
    repository: SqliteLocalStateRepository, connection: sqlite3.Connection
) -> None:
    repository.get_or_create_node_id(_START)
    repository.get_or_create_node_id(_START + timedelta(days=1))
    row = connection.execute("SELECT value FROM node_runtime WHERE key = 'created_at'").fetchone()
    assert row == ("2026-06-11T12:00:00.000000+00:00",)


def test_node_id_creation_failure_is_wrapped_and_rolled_back(
    repository: SqliteLocalStateRepository, connection: sqlite3.Connection
) -> None:
    # 'created_at' pre-existing -> the two-row INSERT violates the PK -> full rollback.
    connection.execute("INSERT INTO node_runtime (key, value) VALUES ('created_at', 'already')")
    with pytest.raises(PersistenceError, match="UNIQUE"):
        repository.get_or_create_node_id(_START)
    assert connection.execute(_NODE_ID_QUERY).fetchone() is None


def test_a_naive_created_at_does_not_wedge_the_connection(
    repository: SqliteLocalStateRepository, connection: sqlite3.Connection
) -> None:
    # utc_iso raises ValueError on a naive instant; a NON-sqlite failure must
    # NEVER leave the connection in_transaction (otherwise every subsequent call dies with
    # "cannot start a transaction within a transaction", a misleading diagnostic).
    with pytest.raises(ValueError, match="aware"):
        repository.get_or_create_node_id(datetime(2026, 6, 11, 12))
    assert connection.in_transaction is False  # healthy connection, no zombie transaction
    assert connection.execute(_NODE_ID_QUERY).fetchone() is None  # nothing half-written
    assert uuid.UUID(repository.get_or_create_node_id(_START))  # the connection stays usable


# --- port satisfaction ------------------------------------------------------------------


def test_repository_satisfies_the_port_structurally(
    repository: SqliteLocalStateRepository,
) -> None:
    port: LocalStateRepository = repository  # mypy proves structural satisfaction
    assert port.reevaluated_policy_fingerprint() is None


# --- reevaluated policy fingerprint (spec §7.1: startup re-evaluation gate) ------------


def test_last_backfill_policy_is_none_before_any_set(
    repository: SqliteLocalStateRepository,
) -> None:
    assert repository.reevaluated_policy_fingerprint() is None


def test_set_last_backfill_policy_then_read_back(
    repository: SqliteLocalStateRepository,
) -> None:
    repository.set_reevaluated_policy_fingerprint("abc")
    assert repository.reevaluated_policy_fingerprint() == "abc"


def test_set_last_backfill_policy_overwrites_on_a_second_call(
    repository: SqliteLocalStateRepository,
) -> None:
    repository.set_reevaluated_policy_fingerprint("abc")
    repository.set_reevaluated_policy_fingerprint("def")
    assert repository.reevaluated_policy_fingerprint() == "def"
