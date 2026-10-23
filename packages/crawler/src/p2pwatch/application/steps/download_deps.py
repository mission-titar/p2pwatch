"""The download loop's dependencies, assembled once by the composition."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import timedelta

from catalog_matching.domain.models import TargetSegment
from p2pwatch.application.ports.driven.decision_reader import DecisionReader
from p2pwatch.application.ports.driven.download_client import DownloadClient
from p2pwatch.application.ports.driven.free_space_meter import FreeSpaceMeter
from p2pwatch.application.ports.driven.logger import Logger
from p2pwatch.application.ports.driven.monotonic_clock import MonotonicClock
from p2pwatch.application.ports.driven.observation_reader import ObservationReader
from p2pwatch.application.ports.driven.source_client import SourceClient
from p2pwatch.application.ports.driven.source_point_reader import SourcePointReader
from p2pwatch.application.ports.driven.source_point_writer import SourcePointWriter
from p2pwatch.application.ports.driven.tracked_download_reader import TrackedDownloadReader
from p2pwatch.application.ports.driven.tracked_download_writer import TrackedDownloadWriter
from p2pwatch.application.ports.driven.wall_clock import WallClock
from p2pwatch.application.steps.observability_dispatcher import ObservabilityDispatcher
from p2pwatch.domain.edge_state import EdgeState
from p2pwatch.domain.file_key import FileKey
from p2pwatch.domain.monotonic_instant import MonotonicInstant


@dataclass
class DownloadDeps:
    """Dependencies of the download loop (composition assembles them once).

    ``targets`` serves the ``target_id → status`` lookup (pure policy). ``free_space_meter``
    measures the free space of the filesystem the client writes to (metadata only, no file is
    opened).
    """

    download_client: DownloadClient
    source_client: SourceClient
    tracked_download_writer: TrackedDownloadWriter
    tracked_download_reader: TrackedDownloadReader
    source_point_writer: SourcePointWriter
    source_point_reader: SourcePointReader
    decision_reader: DecisionReader
    observation_reader: ObservationReader
    targets: Sequence[TargetSegment]
    free_space_meter: FreeSpaceMeter
    min_free_bytes: int
    lost_after: timedelta
    poll_interval_seconds: float
    reappeared_after: timedelta
    sources_interval: timedelta
    time_between_source_reads: timedelta
    wall_clock: WallClock
    monotonic_clock: MonotonicClock
    observability_dispatcher: ObservabilityDispatcher
    logger: Logger
    disk_low_edge: EdgeState = field(default_factory=EdgeState, kw_only=True)  # low-disk warning
    # The sources step's last start.
    sources_read_at: MonotonicInstant | None = field(default=None, kw_only=True)
    # Each queued or downloading download's instant from which it counts as lost.
    loss_deadline_by_file: dict[FileKey, MonotonicInstant] = field(
        default_factory=dict, kw_only=True
    )
