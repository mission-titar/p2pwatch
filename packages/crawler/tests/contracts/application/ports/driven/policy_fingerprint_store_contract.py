"""The promise of the ``PolicyFingerprintReader`` and ``PolicyFingerprintWriter`` pair."""

from abc import ABC, abstractmethod
from typing import Protocol

import pytest


class PolicyFingerprintStore(Protocol):
    """Both ports of the pair, which one store implements."""

    def read_policy_fingerprint(self) -> str | None: ...

    def set_policy_fingerprint(self, fingerprint: str) -> None: ...


class PolicyFingerprintStoreContract(ABC):
    @pytest.fixture
    @abstractmethod
    def policy_fingerprint_store(self) -> PolicyFingerprintStore:
        """A store holding no fingerprint yet."""

    def test_no_policy_fingerprint_is_read_before_one_is_set(
        self, policy_fingerprint_store: PolicyFingerprintStore
    ) -> None:
        assert policy_fingerprint_store.read_policy_fingerprint() is None

    def test_a_set_policy_fingerprint_is_read_back(
        self, policy_fingerprint_store: PolicyFingerprintStore
    ) -> None:
        policy_fingerprint_store.set_policy_fingerprint("abc")
        assert policy_fingerprint_store.read_policy_fingerprint() == "abc"

    def test_a_second_policy_fingerprint_replaces_the_first(
        self, policy_fingerprint_store: PolicyFingerprintStore
    ) -> None:
        policy_fingerprint_store.set_policy_fingerprint("abc")
        policy_fingerprint_store.set_policy_fingerprint("def")
        assert policy_fingerprint_store.read_policy_fingerprint() == "def"
