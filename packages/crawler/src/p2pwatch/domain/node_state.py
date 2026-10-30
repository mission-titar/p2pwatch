"""What a node holds of its own: its identity, its tracked downloads and its search backoffs."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from catalog_matching.domain.identifiers import TargetId
from p2pwatch.domain.download.states import DownloadState, FailureReason, WaitingReason
from p2pwatch.domain.file_key import FileKey
from p2pwatch.domain.identifiers import NodeId
from p2pwatch.domain.search.backoff import BackoffKey, BackoffState


@dataclass(kw_only=True, frozen=True)
class TrackedDownload:
    """A download with a row in ``downloads``, whatever its state."""

    file: FileKey
    target_id: TargetId
    state: DownloadState
    queued_at: datetime
    completed_at: datetime | None
    latest_progress_at: datetime | None  # None until its bytes grow
    waiting_reason: WaitingReason | None
    failure_reason: FailureReason | None


@dataclass(kw_only=True, frozen=True)
class NodeState:
    """``node_id`` and ``created_at`` are ``None`` until the node first records its id."""

    node_id: NodeId | None
    created_at: datetime | None
    downloads: tuple[TrackedDownload, ...]
    backoff_state_by_key: Mapping[BackoffKey, BackoffState]
