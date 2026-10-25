import pytest

from tests.contracts.application.ports.driven.policy_fingerprint_store_contract import (
    PolicyFingerprintStoreContract,
)
from tests.fakes.adapters.driven.fake_policy_fingerprint_store import FakePolicyFingerprintStore


class TestFakePolicyFingerprintStore(PolicyFingerprintStoreContract):
    @pytest.fixture
    def policy_fingerprint_store(self) -> FakePolicyFingerprintStore:
        return FakePolicyFingerprintStore(stored_fingerprint=None)
