"""``ObservationReader``: reads the catalog's observations; synchronous, as every catalog port
(spec data-model §3)."""

from abc import ABC, abstractmethod

from p2pwatch.domain.file_key import FileKey
from p2pwatch.domain.observation import FileObservation


class ObservationReader(ABC):
    """Reads a file's observations; every read returns a :class:`FileObservation` whole."""

    @abstractmethod
    def read_latest_observation(self, file: FileKey) -> FileObservation | None:
        """The file's most recent observation, ``None`` for an unknown file."""

    @abstractmethod
    def read_best_observation(self, file: FileKey) -> FileObservation | None:
        """The observation of its clean filename: the most sourced, then the latest; ``None`` for a
        file never observed."""

    @abstractmethod
    def read_known_filenames(self, file: FileKey) -> tuple[str, ...]:
        """Every distinct filename of the file, sorted."""
