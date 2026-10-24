"""Names a downloaded file in its notifications: its best filename, its target titles."""

from collections.abc import Sequence

from catalog_matching.domain.models import TargetSegment
from p2pwatch.application.ports.driven.decision_reader import DecisionReader
from p2pwatch.application.ports.driven.observation_reader import ObservationReader
from p2pwatch.application.ports.driven.tracked_download_reader import TrackedDownloadReader
from p2pwatch.domain.file_key import FileKey
from p2pwatch.domain.observability.events import TargetTitle


class DownloadLabeler:
    """Names a downloaded file in its notifications, for the tracker and the source watcher."""

    def __init__(
        self,
        *,
        observation_reader: ObservationReader,
        decision_reader: DecisionReader,
        tracked_download_reader: TrackedDownloadReader,
        targets: Sequence[TargetSegment],
    ) -> None:
        self._observation_reader = observation_reader
        self._decision_reader = decision_reader
        self._tracked_download_reader = tracked_download_reader
        self._title_by_target_id = {target.target_id: target.title for target in targets}

    def best_filename(self, file: FileKey) -> str:
        """The clean filename; the native id names a file whose observations are gone."""
        best = self._observation_reader.read_best_observation(file)
        return file.native_id if best is None else best.reported_file.filename

    def target_titles(self, file: FileKey) -> tuple[TargetTitle, ...]:
        """Every download target of the file, else the one it was queued for (the decision may
        have dropped since), each with its title."""
        target_ids = [
            c.target_id for c in self._decision_reader.read_download_candidates() if c.file == file
        ]
        if (
            not target_ids
            and (queued := self._tracked_download_reader.read_queued_target_id(file)) is not None
        ):
            target_ids = [queued]
        return tuple(
            TargetTitle(target_id, self._title_by_target_id.get(target_id, ""))
            for target_id in target_ids
        )
