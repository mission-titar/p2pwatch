"""``SourceReader``: reads the sources the catalog recorded."""

from abc import ABC, abstractmethod

from p2pwatch.domain.file_key import FileKey
from p2pwatch.domain.identifiers import SourceId
from p2pwatch.domain.known_source import KnownSource
from p2pwatch.domain.sharing_period import PeriodWindow, SharingPeriod
from p2pwatch.domain.source_history import SourceHistory, SourceNameHistory


class SourceReader(ABC):
    """Reads the catalog's sources from any thread. A source passes ``search_text`` when its user
    hash starts with it or a name it carried holds it, as typed, case and accents ignored."""

    @abstractmethod
    def read_known_sources(
        self, *, search_text: str | None, limit: int, offset: int
    ) -> tuple[KnownSource, ...]:
        """The sources with a user hash passing ``search_text``, last seen first, then on
        ``source_id`` ascending: at most ``limit`` of them from ``offset``."""

    @abstractmethod
    def read_source_count(self, *, search_text: str | None) -> int:
        """How many sources ``read_known_sources`` pages through for this ``search_text``."""

    @abstractmethod
    def read_source_history(
        self, source_id: SourceId, *, limit: int, offset: int, window: PeriodWindow
    ) -> SourceHistory | None:
        """The source's names from ``offset``, at most ``limit``, and its periods in ``window``;
        ``None`` for a source never recorded."""

    @abstractmethod
    def read_source_name_history(
        self, source_name: str, *, limit: int, offset: int, window: PeriodWindow
    ) -> SourceNameHistory | None:
        """The sources that carried the name from ``offset``, at most ``limit``, and its periods
        without a user hash in ``window``; ``None`` for a name never recorded."""

    @abstractmethod
    def read_sharing_periods(
        self, file: FileKey, *, window: PeriodWindow
    ) -> tuple[SharingPeriod, ...]:
        """The file's sharing periods in ``window``, newest first; cut at its edges."""
