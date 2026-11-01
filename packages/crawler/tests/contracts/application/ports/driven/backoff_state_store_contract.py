"""The promise of the ``BackoffStateReader`` and ``BackoffStateWriter`` pair."""

from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta

import pytest

from p2pwatch.application.ports.driven.backoff_state_reader import BackoffStateReader
from p2pwatch.application.ports.driven.backoff_state_writer import BackoffStateWriter
from p2pwatch.domain.identifiers import Channel, ClientName
from p2pwatch.domain.search.backoff import BackoffKey, BackoffState

_STARTED_AT = datetime(2026, 6, 12, 10, 0, 0, 123456, tzinfo=UTC)
_BACKOFF = {
    BackoffKey(client_name=ClientName("amule-1"), channel=Channel("kad")): BackoffState(
        attempts=2, started_at=_STARTED_AT, delay=timedelta(seconds=300)
    ),
    BackoffKey(client_name=ClientName("amule-1"), channel=None): BackoffState(
        attempts=1, started_at=_STARTED_AT, delay=timedelta(seconds=2.75)
    ),
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
        self, *, writer: BackoffStateWriter, reader: BackoffStateReader
    ) -> None:
        writer.set_backoff_states(_BACKOFF)
        assert reader.read_backoff_states() == _BACKOFF

    def test_a_save_replaces_every_backoff_state_saved_before(
        self, *, writer: BackoffStateWriter, reader: BackoffStateReader
    ) -> None:
        later = {
            BackoffKey(client_name=ClientName("amule-1"), channel=None): BackoffState(
                attempts=2, started_at=_STARTED_AT, delay=timedelta(seconds=4)
            ),
            BackoffKey(client_name=ClientName("amule-1"), channel=Channel("ed2k")): BackoffState(
                attempts=1, started_at=_STARTED_AT, delay=timedelta(seconds=2)
            ),
        }
        writer.set_backoff_states(_BACKOFF)
        writer.set_backoff_states(later)
        assert reader.read_backoff_states() == later

    def test_an_empty_save_replaces_every_backoff_state_saved_before(
        self, *, writer: BackoffStateWriter, reader: BackoffStateReader
    ) -> None:
        writer.set_backoff_states(_BACKOFF)
        writer.set_backoff_states({})
        assert reader.read_backoff_states() == {}

    def test_a_backoff_state_is_read_with_its_start_aware_in_utc(
        self, *, writer: BackoffStateWriter, reader: BackoffStateReader
    ) -> None:
        writer.set_backoff_states(_BACKOFF)
        starts = [state.started_at for state in reader.read_backoff_states().values()]
        assert [started_at.utcoffset() for started_at in starts] == [timedelta(0), timedelta(0)]
