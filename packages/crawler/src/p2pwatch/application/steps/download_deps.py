"""The download loop's dependencies, assembled once by the composition."""

from dataclasses import dataclass

from p2pwatch.application.ports.driven.download_client import DownloadClient
from p2pwatch.application.ports.driven.logger import Logger
from p2pwatch.application.ports.driven.monotonic_clock import MonotonicClock
from p2pwatch.application.steps.download_decider import DownloadDecider
from p2pwatch.application.steps.download_starter import DownloadStarter
from p2pwatch.application.steps.download_tracker import DownloadTracker
from p2pwatch.application.steps.source_watcher import SourceWatcher


@dataclass
class DownloadDeps:
    """Dependencies of the download loop (composition assembles them once)."""

    download_client: DownloadClient
    poll_interval_seconds: float
    monotonic_clock: MonotonicClock
    logger: Logger
    download_tracker: DownloadTracker
    download_decider: DownloadDecider
    download_starter: DownloadStarter
    source_watcher: SourceWatcher
