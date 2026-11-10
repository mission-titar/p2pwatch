import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from p2pwatch.adapters.driven.persistence_sqlite.sqlite_policy_fingerprint_store import (
    SqlitePolicyFingerprintStore,
)
from tests.contracts.application.ports.driven.policy_fingerprint_store_contract import (
    PolicyFingerprintStoreContract,
)
from tests.support.adapters.driven.persistence_sqlite.refused_writes import (
    StorageRefusal,
    refusing,
)
from tests.support.adapters.driven.persistence_sqlite.sqlite_database_opener import open_local
from tests.support.refused_writes import RefuseWrites


class TestSqlitePolicyFingerprintStore(PolicyFingerprintStoreContract):
    @pytest.fixture
    def connection(self, tmp_path: Path) -> Iterator[sqlite3.Connection]:
        connection = open_local(tmp_path / "local.db")
        yield connection
        connection.close()

    @pytest.fixture
    def policy_fingerprint_store(
        self, connection: sqlite3.Connection
    ) -> SqlitePolicyFingerprintStore:
        return SqlitePolicyFingerprintStore(connection)

    @pytest.fixture
    def writer(
        self, policy_fingerprint_store: SqlitePolicyFingerprintStore
    ) -> SqlitePolicyFingerprintStore:
        return policy_fingerprint_store

    @pytest.fixture
    def reader(
        self, policy_fingerprint_store: SqlitePolicyFingerprintStore
    ) -> SqlitePolicyFingerprintStore:
        return policy_fingerprint_store

    @pytest.fixture(params=list(StorageRefusal), ids=str)
    def refuse_writes(
        self, *, request: pytest.FixtureRequest, connection: sqlite3.Connection
    ) -> RefuseWrites:
        return refusing(connection, refusal=request.param)
