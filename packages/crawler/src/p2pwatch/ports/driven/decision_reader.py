"""``DecisionReader``: reads the catalog's latest verdicts; synchronous, as every catalog port
(spec data-model §3)."""

from abc import ABC, abstractmethod

from catalog_matching.domain.engine import DecisionRecord
from p2pwatch.domain.download.candidate import DownloadCandidate
from p2pwatch.domain.file_key import FileKey


class DecisionReader(ABC):
    """Reads the latest verdicts."""

    @abstractmethod
    def read_latest_decisions(self, file: FileKey) -> dict[str, DecisionRecord]:
        """The latest :class:`DecisionRecord` per target (spec §7), a ``retracted`` one included,
        the legacy ``target_id=""`` sentinel excluded."""

    @abstractmethod
    def read_download_candidates(self) -> tuple[DownloadCandidate, ...]:
        """Every file and target whose latest verdict is tier=download (spec download §5)."""
