"""The promise of the ``PolicyFingerprintReader`` and ``PolicyFingerprintWriter`` pair."""

from abc import ABC, abstractmethod
from random import Random

import pytest

from p2pwatch.application.ports.driven.policy_fingerprint_reader import PolicyFingerprintReader
from p2pwatch.application.ports.driven.policy_fingerprint_writer import PolicyFingerprintWriter
from tests.support.draws import draw_text


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
        self,
        *,
        randomness: Random,
        writer: PolicyFingerprintWriter,
        reader: PolicyFingerprintReader,
    ) -> None:
        fingerprint = draw_text(randomness)
        writer.set_policy_fingerprint(fingerprint)
        assert reader.read_policy_fingerprint() == fingerprint

    def test_a_second_policy_fingerprint_replaces_the_first(
        self,
        *,
        randomness: Random,
        writer: PolicyFingerprintWriter,
        reader: PolicyFingerprintReader,
    ) -> None:
        writer.set_policy_fingerprint(draw_text(randomness))
        latest = draw_text(randomness)
        writer.set_policy_fingerprint(latest)
        assert reader.read_policy_fingerprint() == latest
