import pytest

from tests.contracts.application.ports.driven.policy_fingerprint_store_contract import (
    PolicyFingerprintPorts,
    PolicyFingerprintStoreContract,
)
from tests.fakes.adapters.driven.fake_policy_fingerprint_store import FakePolicyFingerprintStore


class TestFakePolicyFingerprintStore(PolicyFingerprintStoreContract):
    @pytest.fixture
    def policy_fingerprint_store(self) -> FakePolicyFingerprintStore:
        return FakePolicyFingerprintStore(stored_fingerprint=None)

    @pytest.fixture
    def policy_fingerprint_ports(
        self, policy_fingerprint_store: FakePolicyFingerprintStore
    ) -> PolicyFingerprintPorts:
        return PolicyFingerprintPorts(
            writer=policy_fingerprint_store, reader=policy_fingerprint_store
        )
