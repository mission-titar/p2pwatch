"""``DecisionReader``: reads the catalog's latest verdicts; synchronous, as every catalog port
(spec data-model §3)."""

from abc import ABC, abstractmethod

from catalog_matching.domain.identifiers import TargetId
from p2pwatch.domain.download.candidate import DownloadCandidate
from p2pwatch.domain.file_key import FileKey
from p2pwatch.domain.file_target_decision import FileTargetDecision


class DecisionReader(ABC):
    """Reads the latest verdicts."""

    @abstractmethod
    def read_latest_decisions(self, file: FileKey) -> dict[TargetId, FileTargetDecision]:
        """The latest decision per target (spec §7), a :class:`Retraction` included, the legacy
        ``target_id=""`` sentinel excluded."""

    @abstractmethod
    def read_download_candidates(self) -> tuple[DownloadCandidate, ...]:
        """Each file and target whose latest verdict by any node is tier=download, a file's by
        target id: a merge joins trusted peers; a download the webui shows belongs in the client."""
