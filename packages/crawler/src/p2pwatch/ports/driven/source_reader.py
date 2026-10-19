"""``SourceReader``: reads the sources the catalog recorded."""

from abc import ABC, abstractmethod

from p2pwatch.domain.file_key import FileKey
from p2pwatch.domain.sharing_period import PeriodWindow, SharingPeriod


class SourceReader(ABC):
    """Reads the catalog's sources from any thread."""

    @abstractmethod
    def read_sharing_periods(
        self, file: FileKey, window: PeriodWindow
    ) -> tuple[SharingPeriod, ...]:
        """The file's sharing periods in ``window``, newest first; cut at its edges."""
