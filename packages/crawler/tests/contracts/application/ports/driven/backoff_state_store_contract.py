"""The promise of the ``BackoffStateReader`` and ``BackoffStateWriter`` pair."""

from abc import ABC, abstractmethod
from datetime import UTC
from random import Random

import pytest

from p2pwatch.application.ports.driven.backoff_state_reader import BackoffStateReader
from p2pwatch.application.ports.driven.backoff_state_writer import BackoffStateWriter
from p2pwatch.domain.search.backoff import BackoffKey, BackoffState
from tests.support.domain.search.backoff import draw_backoff_key, draw_backoff_state


def _draw_client_backoff(
    randomness: Random, *, whole_client: BackoffKey
) -> dict[BackoffKey, BackoffState]:
    """Drawn states of ``whole_client`` and of a drawn channel of its client."""
    channel = draw_backoff_key(randomness, has_channel=True, client_name=whole_client.client_name)
    return {
        whole_client: draw_backoff_state(randomness),
        channel: draw_backoff_state(randomness),
    }


class BackoffStateStoreContract(ABC):
    @pytest.fixture
    @abstractmethod
    def writer(self) -> BackoffStateWriter:
        """The writer of a store holding no backoff state yet."""

    @pytest.fixture
    @abstractmethod
    def reader(self) -> BackoffStateReader:
        """The reader of the writer's store."""

    def test_no_backoff_state_is_read_before_the_first_save(
        self, reader: BackoffStateReader
    ) -> None:
        assert reader.read_backoff_states() == {}

    def test_the_backoff_states_saved_are_read_back(
        self, *, randomness: Random, writer: BackoffStateWriter, reader: BackoffStateReader
    ) -> None:
        whole_client = draw_backoff_key(randomness, has_channel=False)
        backoff_state_by_key = _draw_client_backoff(randomness, whole_client=whole_client)
        writer.set_backoff_states(backoff_state_by_key)
        assert reader.read_backoff_states() == backoff_state_by_key

    def test_a_save_replaces_every_backoff_state_saved_before(
        self, *, randomness: Random, writer: BackoffStateWriter, reader: BackoffStateReader
    ) -> None:
        whole_client = draw_backoff_key(randomness, has_channel=False)
        writer.set_backoff_states(_draw_client_backoff(randomness, whole_client=whole_client))
        latest = _draw_client_backoff(randomness, whole_client=whole_client)
        writer.set_backoff_states(latest)
        assert reader.read_backoff_states() == latest

    def test_an_empty_save_replaces_every_backoff_state_saved_before(
        self, *, randomness: Random, writer: BackoffStateWriter, reader: BackoffStateReader
    ) -> None:
        whole_client = draw_backoff_key(randomness, has_channel=False)
        writer.set_backoff_states(_draw_client_backoff(randomness, whole_client=whole_client))
        writer.set_backoff_states({})
        assert reader.read_backoff_states() == {}

    def test_a_backoff_state_is_read_with_its_start_aware_in_utc(
        self, *, randomness: Random, writer: BackoffStateWriter, reader: BackoffStateReader
    ) -> None:
        whole_client = draw_backoff_key(randomness, has_channel=False)
        writer.set_backoff_states(_draw_client_backoff(randomness, whole_client=whole_client))
        starts = [state.started_at for state in reader.read_backoff_states().values()]
        assert [started_at.utcoffset() for started_at in starts] == [UTC.utcoffset(None)] * 2
