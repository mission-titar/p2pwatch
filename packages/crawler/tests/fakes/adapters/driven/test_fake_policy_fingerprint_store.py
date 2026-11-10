import pytest

from tests.contracts.application.ports.driven.policy_fingerprint_store_contract import (
    PolicyFingerprintStoreContract,
)
from tests.fakes.adapters.driven.fake_policy_fingerprint_store import FakePolicyFingerprintStore
from tests.support.refused_writes import RefuseWrites


class TestFakePolicyFingerprintStore(PolicyFingerprintStoreContract):
    @pytest.fixture
    def policy_fingerprint_store(self) -> FakePolicyFingerprintStore:
        return FakePolicyFingerprintStore(stored_fingerprint=None)

    @pytest.fixture
    def writer(
        self, policy_fingerprint_store: FakePolicyFingerprintStore
    ) -> FakePolicyFingerprintStore:
        return policy_fingerprint_store

    @pytest.fixture
    def reader(
        self, policy_fingerprint_store: FakePolicyFingerprintStore
    ) -> FakePolicyFingerprintStore:
        return policy_fingerprint_store

    @pytest.fixture
    def refuse_writes(self) -> RefuseWrites:
        pytest.skip("a fake's memory refuses no write")
