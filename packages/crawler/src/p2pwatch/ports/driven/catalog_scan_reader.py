"""``CatalogScanReader``: walks the whole catalog; synchronous, as every catalog port (spec
data-model §3)."""

from abc import ABC, abstractmethod
from collections.abc import Iterator

from p2pwatch.domain.observation import FileObservation


class CatalogScanReader(ABC):
    """Walks the whole catalog, for the startup re-evaluation (spec re-evaluation §6)."""

    @abstractmethod
    def read_file_count(self) -> int:
        """The number of files, the re-evaluation's progress total."""

    @abstractmethod
    def iter_latest_observations(self) -> Iterator[FileObservation]:
        """Every file's latest observation, streamed."""
