"""The promise of the ``PolicyFingerprintReader`` and ``PolicyFingerprintWriter`` pair."""

from abc import ABC, abstractmethod
from random import Random

import pytest

from p2pwatch.application.ports.driven.policy_fingerprint_reader import PolicyFingerprintReader
from p2pwatch.application.ports.driven.policy_fingerprint_writer import PolicyFingerprintWriter
from p2pwatch.domain.store_error import StoreError
from tests.support.draws import draw_text
from tests.support.refused_writes import RefuseWrites, draw_long_text


class PolicyFingerprintStoreContract(ABC):
    @pytest.fixture
    @abstractmethod
    def writer(self) -> PolicyFingerprintWriter:
        """The writer of a store holding no fingerprint yet."""

    @pytest.fixture
    @abstractmethod
    def reader(self) -> PolicyFingerprintReader:
        """The reader of the writer's store."""

    @pytest.fixture
    @abstractmethod
    def refuse_writes(self) -> RefuseWrites:
        """Makes the writer's store refuse every write."""

    def test_a_fingerprint_its_store_refuses_raises_store_error_and_is_not_set(
        self,
        *,
        randomness: Random,
        writer: PolicyFingerprintWriter,
        reader: PolicyFingerprintReader,
        refuse_writes: RefuseWrites,
    ) -> None:
        refuse_writes()
        with pytest.raises(StoreError):
            writer.set_policy_fingerprint(draw_long_text(randomness))
        assert reader.read_policy_fingerprint() is None

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
