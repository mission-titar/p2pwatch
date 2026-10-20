"""The catalog's ports: its durable memory, append-only (spec data-model §4).

SYNCHRONOUS (spec §3: a local write is sub-millisecond; if plan C wants to isolate itself, it will
wrap it in ``asyncio.to_thread`` without touching this layer). The use case gives each write its
instant and its ``node_id``: a :class:`FileObservation` carries its ``observed_at``,
``record_decision`` receives the file key, the instant and the ``node_id`` ALONGSIDE the decision
(``MatchDecision`` carries none: a domain without persistence columns).
"""

from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime

from catalog_matching.domain.engine import DecisionRecord, MatchDecision
from p2pwatch.domain.file_key import FileKey
from p2pwatch.domain.observation import FileObservation


@dataclass(frozen=True)
class DownloadCandidate:
    """A file whose latest verdict for ``target_id`` is tier=download, for the download loop."""

    file: FileKey
    target_id: str


class ObservationWriter(ABC):
    """Appends what the network reported of a file."""

    @abstractmethod
    def record_observation(self, observation: FileObservation, node_id: str) -> None:
        """Appends ``observation``, as ``node_id`` observed it."""


class ObservationReader(ABC):
    """Reads a file's observations; every read returns a :class:`FileObservation` whole."""

    @abstractmethod
    def read_latest_observation(self, file: FileKey) -> FileObservation | None:
        """The file's most recent observation, ``None`` for an unknown file."""

    @abstractmethod
    def read_best_observation(self, file: FileKey) -> FileObservation | None:
        """The observation of its clean filename: the most sourced, then the latest."""

    @abstractmethod
    def read_known_filenames(self, file: FileKey) -> tuple[str, ...]:
        """Every distinct filename of the file, sorted."""


class DecisionWriter(ABC):
    """Appends the matcher's verdicts on a file, per target."""

    @abstractmethod
    def record_decision(
        self, file: FileKey, decision: MatchDecision, decided_at: datetime, node_id: str
    ) -> None:
        """Appends ``decision`` for its target."""

    @abstractmethod
    def record_retraction(
        self, file: FileKey, target_id: str, decided_at: datetime, node_id: str
    ) -> None:
        """Appends a ``retracted`` row (spec §7): the append-only table has no delete."""


class DecisionReader(ABC):
    """Reads the latest verdicts."""

    @abstractmethod
    def read_latest_decisions(self, file: FileKey) -> dict[str, DecisionRecord]:
        """The latest :class:`DecisionRecord` per target (spec §7), a ``retracted`` one included,
        the legacy ``target_id=""`` sentinel excluded."""

    @abstractmethod
    def read_download_candidates(self) -> tuple[DownloadCandidate, ...]:
        """Every file and target whose latest verdict is tier=download (spec download §5)."""


class CatalogScanner(ABC):
    """Walks the whole catalog, for the startup re-evaluation (spec re-evaluation §6)."""

    @abstractmethod
    def read_file_count(self) -> int:
        """The number of files, the re-evaluation's progress total."""

    @abstractmethod
    def iter_latest_observations(self) -> Iterator[FileObservation]:
        """Every file's latest observation, streamed."""
