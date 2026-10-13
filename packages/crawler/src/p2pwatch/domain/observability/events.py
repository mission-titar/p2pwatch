"""Observability events: PURE business facts (spec Plan E §3-4).

DOMAIN layer (pure). One FROZEN dataclass per salient observable fact; tagged union
``Event``. Business fields ONLY: no notion of log/metric/notif (that is ``policy.describe``'s
job). Recurring failure facts carry ``first_occurrence`` (computed by the application via
``EdgeState``) for notification anti-spam (E-D8).
"""

from dataclasses import dataclass
from typing import Literal

from p2pwatch.domain.file_key import FileKey
from p2pwatch.domain.source import SourceKey


@dataclass(frozen=True)
class SearchExecuted:
    client_name: str
    channel: str
    result_count: int


@dataclass(frozen=True)
class ClientUnreachable:
    client_name: str


@dataclass(frozen=True)
class SearchFailed:
    client_name: str
    channel: str


@dataclass(frozen=True)
class ObservationRecorded:
    client_name: str
    channel: str


@dataclass(frozen=True)
class DecisionChange:
    target_id: str
    title: str
    previous_tier: str | None  # the persisted tier, None for a target never judged
    new_tier: str  # the fresh tier, or "retracted"


@dataclass(frozen=True)
class TargetTitle:
    target_id: str
    title: str


@dataclass(frozen=True)
class DecisionsRecorded:
    # What one evaluation of a file changed in its judgement, all its targets together.
    file: FileKey
    filename: str  # the clean name, the most sourced
    size_bytes: int
    changes: tuple[DecisionChange, ...]


@dataclass(frozen=True)
class DownloadQueued:
    target_id: str


@dataclass(frozen=True)
class DownloadCompleted:
    file: FileKey
    filename: str  # the clean name, the most sourced
    target_titles: tuple[TargetTitle, ...]  # every download target of the file


type ChannelField = Literal["connected", "connectable"]


@dataclass(frozen=True)
class ChannelStatusSampled:
    # One status reading of a channel; None is unknown (the client's API did not answer).
    client_name: str
    channel: str
    connected: bool | None
    connectable: bool | None


@dataclass(frozen=True)
class ChannelDegraded:
    # A field of a channel has read False for ``seconds``: emitted once until it recovers.
    client_name: str
    channel: str
    field: ChannelField
    seconds: float


@dataclass(frozen=True)
class ChannelRecovered:
    client_name: str
    channel: str
    field: ChannelField


@dataclass(frozen=True)
class ClientUnreachableLasting:
    # The client's API has not answered for ``seconds``: emitted once until it answers.
    client_name: str
    seconds: float


@dataclass(frozen=True)
class ClientReachableAgain:
    client_name: str


@dataclass(frozen=True)
class FreeSpaceSampled:
    free_bytes: int  # the download cycle's statvfs on the output directory


@dataclass(frozen=True)
class DiskSpaceLow:
    # Emitted only on the crossing below the floor: the download loop owns the edge.
    free_bytes: int
    min_free_bytes: int


@dataclass(frozen=True)
class SourceFirstUseful:
    # A source read useful for the first time on this node (source points spec, D5).
    source: SourceKey
    source_name: str | None
    file: FileKey
    filename: str  # the clean name, the most sourced
    target_titles: tuple[TargetTitle, ...]  # none for a file without one


@dataclass(frozen=True)
class SourceReappeared:
    # A source reappeared: useful after ``absent_seconds`` neither useful nor not useful here (D9).
    source: SourceKey
    source_name: str | None
    file: FileKey
    filename: str
    target_titles: tuple[TargetTitle, ...]
    absent_seconds: float


@dataclass(frozen=True)
class CrawlerStarted:
    download_enabled: bool


type Event = (
    SearchExecuted
    | ClientUnreachable
    | SearchFailed
    | ObservationRecorded
    | DecisionsRecorded
    | DownloadQueued
    | DownloadCompleted
    | ChannelStatusSampled
    | ChannelDegraded
    | ChannelRecovered
    | ClientUnreachableLasting
    | ClientReachableAgain
    | FreeSpaceSampled
    | DiskSpaceLow
    | SourceFirstUseful
    | SourceReappeared
    | CrawlerStarted
)
