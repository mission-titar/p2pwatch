"""The two reads of a downloaded file two stages share: its target titles, its best filename."""

from p2pwatch.application.steps.download_deps import DownloadDeps
from p2pwatch.domain.file_key import FileKey
from p2pwatch.domain.observability.events import TargetTitle


def target_titles(deps: DownloadDeps, file: FileKey) -> tuple[TargetTitle, ...]:
    """Every download target of the file, else the one it was queued for (the decision may have
    dropped since), each with its title."""
    target_ids = [
        c.target_id for c in deps.decision_reader.read_download_candidates() if c.file == file
    ]
    if (
        not target_ids
        and (queued := deps.tracked_download_reader.read_queued_target_id(file)) is not None
    ):
        target_ids = [queued]
    titles = {target.target_id: target.title for target in deps.targets}
    return tuple(TargetTitle(target_id, titles.get(target_id, "")) for target_id in target_ids)


def best_filename(deps: DownloadDeps, file: FileKey) -> str:
    """The clean filename; the native id names a file whose observations are gone."""
    best = deps.observation_reader.read_best_observation(file)
    return file.native_id if best is None else best.reported_file.filename
