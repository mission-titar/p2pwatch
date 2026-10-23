"""The two reads of a downloaded file two stages share: its target titles, its best filename."""

from collections.abc import Sequence

from catalog_matching.domain.models import TargetSegment
from p2pwatch.application.ports.driven.decision_reader import DecisionReader
from p2pwatch.application.ports.driven.observation_reader import ObservationReader
from p2pwatch.application.ports.driven.tracked_download_reader import TrackedDownloadReader
from p2pwatch.domain.file_key import FileKey
from p2pwatch.domain.observability.events import TargetTitle


def target_titles(
    file: FileKey,
    *,
    decision_reader: DecisionReader,
    tracked_download_reader: TrackedDownloadReader,
    targets: Sequence[TargetSegment],
) -> tuple[TargetTitle, ...]:
    """Every download target of the file, else the one it was queued for (the decision may have
    dropped since), each with its title."""
    target_ids = [c.target_id for c in decision_reader.read_download_candidates() if c.file == file]
    if (
        not target_ids
        and (queued := tracked_download_reader.read_queued_target_id(file)) is not None
    ):
        target_ids = [queued]
    titles = {target.target_id: target.title for target in targets}
    return tuple(TargetTitle(target_id, titles.get(target_id, "")) for target_id in target_ids)


def best_filename(file: FileKey, *, observation_reader: ObservationReader) -> str:
    """The clean filename; the native id names a file whose observations are gone."""
    best = observation_reader.read_best_observation(file)
    return file.native_id if best is None else best.reported_file.filename
