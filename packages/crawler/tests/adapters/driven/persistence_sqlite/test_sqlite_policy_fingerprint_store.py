from collections.abc import Iterator
from pathlib import Path

import pytest

from p2pwatch.adapters.driven.persistence_sqlite.sqlite_policy_fingerprint_store import (
    SqlitePolicyFingerprintStore,
)
from tests.contracts.application.ports.driven.policy_fingerprint_store_contract import (
    PolicyFingerprintStoreContract,
)
from tests.support.adapters.driven.persistence_sqlite.sqlite_database_opener import open_local


class TestSqlitePolicyFingerprintStore(PolicyFingerprintStoreContract):
    @pytest.fixture
    def policy_fingerprint_store(self, tmp_path: Path) -> Iterator[SqlitePolicyFingerprintStore]:
        connection = open_local(tmp_path / "local.db")
        yield SqlitePolicyFingerprintStore(connection)
        connection.close()
