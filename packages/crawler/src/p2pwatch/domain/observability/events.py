"""Observability events: PURE business facts (spec Plan E §3-4).

DOMAIN ring (pure). One FROZEN dataclass per salient observable fact; tagged union
``Event``. Business fields ONLY: no notion of log/metric/notification (that is
``policy.plan_observability``'s job). Recurring failure facts carry ``first_occurrence``
(computed by the application via ``EdgeState``) for notification anti-spam (E-D8).
"""

from dataclasses import dataclass
from typing import Literal

from catalog_matching.domain.identifiers import TargetId
from p2pwatch.domain.file_key import FileKey
from p2pwatch.domain.file_target_decision import FileTargetDecision
from p2pwatch.domain.identifiers import Channel, ClientName, NodeId
from p2pwatch.domain.source import SourceKey


@dataclass(kw_only=True, frozen=True)
class SearchExecuted:
    client_name: ClientName
    channel: Channel
    observation_count: int
    skipped_result_count: int  # results the client could not read: a drift of its protocol


@dataclass(kw_only=True, frozen=True)
class ClientUnreachable:
    client_name: ClientName


@dataclass(kw_only=True, frozen=True)
class SearchFailed:
    client_name: ClientName
    channel: Channel


@dataclass(kw_only=True, frozen=True)
class ObservationRecorded:
    client_name: ClientName
    channel: Channel


@dataclass(kw_only=True, frozen=True)
class DecisionChange:
    target_id: TargetId
    title: str
    previous_decision: FileTargetDecision | None  # None for a target never judged
    new_decision: FileTargetDecision


@dataclass(kw_only=True, frozen=True)
class TargetTitle:
    target_id: TargetId
    title: str


@dataclass(kw_only=True, frozen=True)
class DecisionsRecorded:
    # What one evaluation of a file changed in its judgement, all its targets together.
    file: FileKey
    filename: str  # the clean name, the most sourced
    size_bytes: int
    changes: tuple[DecisionChange, ...]
    node_id: NodeId


@dataclass(kw_only=True, frozen=True)
class DownloadQueued:
    target_id: TargetId


@dataclass(kw_only=True, frozen=True)
class DownloadCompleted:
    file: FileKey
    filename: str  # the clean name, the most sourced
    target_titles: tuple[TargetTitle, ...]  # every download target of the file, none if unknown
    node_id: NodeId


type ChannelField = Literal["connected", "connectable"]


@dataclass(kw_only=True, frozen=True)
class ChannelStatusSampled:
    # One status reading of a channel; None is unknown (the client's API did not answer).
    client_name: ClientName
    channel: Channel
    connected: bool | None
    connectable: bool | None


@dataclass(kw_only=True, frozen=True)
class ChannelDegraded:
    # A channel's field has read False for ``degraded_for_seconds``: emitted once until it recovers.
    client_name: ClientName
    channel: Channel
    field: ChannelField
    degraded_for_seconds: float
    node_id: NodeId


@dataclass(kw_only=True, frozen=True)
class ChannelRecovered:
    client_name: ClientName
    channel: Channel
    field: ChannelField
    node_id: NodeId


@dataclass(kw_only=True, frozen=True)
class ClientUnreachableLasting:
    # No answer from the client's API for ``unreachable_for_seconds``: emitted once until one comes.
    client_name: ClientName
    unreachable_for_seconds: float
    node_id: NodeId


@dataclass(kw_only=True, frozen=True)
class ClientReachableAgain:
    client_name: ClientName
    node_id: NodeId


@dataclass(kw_only=True, frozen=True)
class FreeSpaceSampled:
    free_bytes: int  # the download cycle's statvfs on the output directory


@dataclass(kw_only=True, frozen=True)
class DiskSpaceLow:
    # Emitted only on the crossing below the floor: the download loop owns the edge.
    free_bytes: int
    min_free_bytes: int
    node_id: NodeId


@dataclass(kw_only=True, frozen=True)
class SourceFirstUseful:
    # A source read useful for the first time on this node (source points spec, D5).
    source: SourceKey
    source_name: str | None
    file: FileKey
    filename: str  # the clean name, the most sourced
    target_titles: tuple[TargetTitle, ...]  # none for a file without one
    node_id: NodeId


@dataclass(kw_only=True, frozen=True)
class SourceReappeared:
    # A source useful after ``absent_for_seconds`` with no point, useful or not useful (D9).
    source: SourceKey
    source_name: str | None
    file: FileKey
    filename: str
    target_titles: tuple[TargetTitle, ...]
    absent_for_seconds: float
    node_id: NodeId


@dataclass(kw_only=True, frozen=True)
class CrawlerStarted:
    download_enabled: bool
    node_id: NodeId


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
