"""The promise of the ``PolicyFingerprintReader`` and ``PolicyFingerprintWriter`` pair."""

from abc import ABC, abstractmethod

import pytest

from p2pwatch.application.ports.driven.policy_fingerprint_reader import PolicyFingerprintReader
from p2pwatch.application.ports.driven.policy_fingerprint_writer import PolicyFingerprintWriter


class PolicyFingerprintStoreContract(ABC):
    @pytest.fixture
    @abstractmethod
    def writer(self) -> PolicyFingerprintWriter:
        """The writer of a store holding no fingerprint yet."""

    @pytest.fixture
    @abstractmethod
    def reader(self) -> PolicyFingerprintReader:
        """The reader of the writer's store."""

    def test_no_policy_fingerprint_is_read_before_one_is_set(
        self, reader: PolicyFingerprintReader
    ) -> None:
        assert reader.read_policy_fingerprint() is None

    def test_a_set_policy_fingerprint_is_read_back(
        self, *, writer: PolicyFingerprintWriter, reader: PolicyFingerprintReader
    ) -> None:
        writer.set_policy_fingerprint("abc")
        assert reader.read_policy_fingerprint() == "abc"

    def test_a_second_policy_fingerprint_replaces_the_first(
        self, *, writer: PolicyFingerprintWriter, reader: PolicyFingerprintReader
    ) -> None:
        writer.set_policy_fingerprint("abc")
        writer.set_policy_fingerprint("def")
        assert reader.read_policy_fingerprint() == "def"
