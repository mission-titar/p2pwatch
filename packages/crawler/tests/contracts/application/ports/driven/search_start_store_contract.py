"""The promise of the ``SearchStartReader`` and ``SearchStartWriter`` pair."""

from abc import ABC, abstractmethod
from datetime import timedelta
from random import Random

import pytest

from p2pwatch.application.ports.driven.search_start_reader import SearchStartReader
from p2pwatch.application.ports.driven.search_start_writer import SearchStartWriter
from p2pwatch.domain.identifiers import Channel, ClientName
from p2pwatch.domain.search.latest_search_start import LatestSearchStart
from p2pwatch.domain.store_error import StoreError
from tests.support.draws import draw_instant, draw_text
from tests.support.refused_writes import RefuseWrites, draw_long_text


def _draw_start(
    randomness: Random, *, channel: Channel | None = None, scope: str | None = None
) -> LatestSearchStart:
    """A start at a drawn instant, its channel and its scope drawn unless given."""
    return LatestSearchStart(
        channel=Channel(draw_text(randomness)) if channel is None else channel,
        scope=draw_text(randomness) if scope is None else scope,
        started_at=draw_instant(randomness),
    )


def _sorted(starts: tuple[LatestSearchStart, ...]) -> list[LatestSearchStart]:
    """The starts by channel then scope, since a read promises no order."""
    return sorted(starts, key=lambda start: (start.channel, start.scope))


class SearchStartStoreContract(ABC):
    @pytest.fixture
    @abstractmethod
    def writer(self) -> SearchStartWriter:
        """The writer of a store holding no search start yet."""

    @pytest.fixture
    @abstractmethod
    def reader(self) -> SearchStartReader:
        """The reader of the writer's store."""

    @pytest.fixture
    @abstractmethod
    def refuse_writes(self) -> RefuseWrites:
        """Makes the writer's store refuse every write."""

    def test_a_start_its_store_refuses_raises_store_error_and_keeps_none(
        self,
        *,
        randomness: Random,
        writer: SearchStartWriter,
        reader: SearchStartReader,
        refuse_writes: RefuseWrites,
    ) -> None:
        client_name = ClientName(draw_long_text(randomness))
        refuse_writes()

        with pytest.raises(StoreError):
            writer.set_latest_start(client_name, start=_draw_start(randomness))

        assert reader.read_latest_starts(client_name) == ()

    def test_no_start_is_read_before_the_first_write(
        self, *, randomness: Random, reader: SearchStartReader
    ) -> None:
        assert reader.read_latest_starts(ClientName(draw_text(randomness))) == ()

    def test_each_start_written_in_its_own_channel_and_scope_is_read_back(
        self, *, randomness: Random, writer: SearchStartWriter, reader: SearchStartReader
    ) -> None:
        client_name = ClientName(draw_text(randomness))
        channel = Channel(draw_text(randomness))
        starts = (
            _draw_start(randomness, channel=channel, scope=""),
            _draw_start(randomness, channel=channel),
            # The same scope in another channel is another start.
            _draw_start(randomness, scope=""),
        )

        for start in starts:
            writer.set_latest_start(client_name, start=start)

        assert _sorted(reader.read_latest_starts(client_name)) == _sorted(starts)

    def test_a_start_replaces_the_earlier_one_of_its_channel_and_scope(
        self, *, randomness: Random, writer: SearchStartWriter, reader: SearchStartReader
    ) -> None:
        client_name = ClientName(draw_text(randomness))
        earlier = _draw_start(randomness)
        latest = _draw_start(randomness, channel=earlier.channel, scope=earlier.scope)

        writer.set_latest_start(client_name, start=earlier)
        writer.set_latest_start(client_name, start=latest)

        assert reader.read_latest_starts(client_name) == (latest,)

    def test_a_client_reads_its_own_starts_and_no_other_clients(
        self, *, randomness: Random, writer: SearchStartWriter, reader: SearchStartReader
    ) -> None:
        own_client, other_client = (
            ClientName(draw_text(randomness)),
            ClientName(draw_text(randomness)),
        )
        own_start = _draw_start(randomness)
        other_start = _draw_start(randomness, channel=own_start.channel, scope=own_start.scope)

        writer.set_latest_start(own_client, start=own_start)
        writer.set_latest_start(other_client, start=other_start)

        assert reader.read_latest_starts(own_client) == (own_start,)

    def test_a_start_is_read_aware_in_utc(
        self, *, randomness: Random, writer: SearchStartWriter, reader: SearchStartReader
    ) -> None:
        client_name = ClientName(draw_text(randomness))
        writer.set_latest_start(client_name, start=_draw_start(randomness))

        starts = reader.read_latest_starts(client_name)

        assert [start.started_at.utcoffset() for start in starts] == [timedelta(0)]
