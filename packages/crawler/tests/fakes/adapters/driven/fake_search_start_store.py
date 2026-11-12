from p2pwatch.application.ports.driven.search_start_reader import SearchStartReader
from p2pwatch.application.ports.driven.search_start_writer import SearchStartWriter
from p2pwatch.domain.identifiers import Channel, ClientName
from p2pwatch.domain.search.latest_search_start import LatestSearchStart
from p2pwatch.domain.store_error import StoreError


class FakeSearchStartStore(SearchStartReader, SearchStartWriter):
    """Keeps each client's latest starts; its reads or its writes raise once told to fail."""

    def __init__(self) -> None:
        self.reads_fail = False
        self.writes_fail = False
        self._start_by_key: dict[tuple[ClientName, Channel, str], LatestSearchStart] = {}

    def read_latest_starts(self, client_name: ClientName) -> tuple[LatestSearchStart, ...]:
        if self.reads_fail:
            raise StoreError("database is locked")
        return tuple(
            start for (owner, _, _), start in self._start_by_key.items() if owner == client_name
        )

    def set_latest_start(self, client_name: ClientName, *, start: LatestSearchStart) -> None:
        if self.writes_fail:
            raise StoreError("database is locked")
        self._start_by_key[client_name, start.channel, start.scope] = start
