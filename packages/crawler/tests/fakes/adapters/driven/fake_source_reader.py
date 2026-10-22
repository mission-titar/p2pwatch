from typing import Any

from p2pwatch.application.ports.driven.source_reader import SourceReader
from p2pwatch.domain.file_key import FileKey
from p2pwatch.domain.known_source import KnownSource
from p2pwatch.domain.sharing_period import PeriodWindow, SharingPeriod
from p2pwatch.domain.source_history import SourceHistory, SourceNameHistory


class FakeSourceReader(SourceReader):
    """Reads what it is given, and keeps each call by its operation's name, with its arguments."""

    def __init__(
        self,
        *,
        known_sources: tuple[KnownSource, ...] = (),
        source_count: int = 0,
        source_history: SourceHistory | None = None,
        source_name_history: SourceNameHistory | None = None,
        sharing_periods: tuple[SharingPeriod, ...] = (),
    ) -> None:
        self._known_sources = known_sources
        self._source_count = source_count
        self._source_history = source_history
        self._source_name_history = source_name_history
        self._sharing_periods = sharing_periods
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def read_known_sources(self, **arguments: Any) -> tuple[KnownSource, ...]:
        self.calls.append(("read_known_sources", arguments))
        return self._known_sources

    def read_source_count(self, **arguments: Any) -> int:
        self.calls.append(("read_source_count", arguments))
        return self._source_count

    def read_source_history(self, source_id: bytes, **arguments: Any) -> SourceHistory | None:
        self.calls.append(("read_source_history", {"source_id": source_id, **arguments}))
        return self._source_history

    def read_source_name_history(
        self, source_name: str, **arguments: Any
    ) -> SourceNameHistory | None:
        self.calls.append(("read_source_name_history", {"source_name": source_name, **arguments}))
        return self._source_name_history

    def read_sharing_periods(
        self, file: FileKey, window: PeriodWindow
    ) -> tuple[SharingPeriod, ...]:
        self.calls.append(("read_sharing_periods", {"file": file, "window": window}))
        return self._sharing_periods
