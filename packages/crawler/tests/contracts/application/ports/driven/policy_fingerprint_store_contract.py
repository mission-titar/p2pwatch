"""The promise of the ``PolicyFingerprintReader`` and ``PolicyFingerprintWriter`` pair."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

import pytest

from p2pwatch.application.ports.driven.policy_fingerprint_reader import PolicyFingerprintReader
from p2pwatch.application.ports.driven.policy_fingerprint_writer import PolicyFingerprintWriter


@dataclass(kw_only=True, frozen=True)
class PolicyFingerprintPorts:
    """The pair's two ports, which one store implements."""

    writer: PolicyFingerprintWriter
    reader: PolicyFingerprintReader


class PolicyFingerprintStoreContract(ABC):
    @pytest.fixture
    @abstractmethod
    def policy_fingerprint_ports(self) -> PolicyFingerprintPorts:
        """The ports of a store holding no fingerprint yet."""

    def test_no_policy_fingerprint_is_read_before_one_is_set(
        self, policy_fingerprint_ports: PolicyFingerprintPorts
    ) -> None:
        assert policy_fingerprint_ports.reader.read_policy_fingerprint() is None

    def test_a_set_policy_fingerprint_is_read_back(
        self, policy_fingerprint_ports: PolicyFingerprintPorts
    ) -> None:
        policy_fingerprint_ports.writer.set_policy_fingerprint("abc")
        assert policy_fingerprint_ports.reader.read_policy_fingerprint() == "abc"

    def test_a_second_policy_fingerprint_replaces_the_first(
        self, policy_fingerprint_ports: PolicyFingerprintPorts
    ) -> None:
        policy_fingerprint_ports.writer.set_policy_fingerprint("abc")
        policy_fingerprint_ports.writer.set_policy_fingerprint("def")
        assert policy_fingerprint_ports.reader.read_policy_fingerprint() == "def"
