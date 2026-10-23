"""What a ``Notifier`` sends an audience, each notification carrying the node that sent it.

Plain values: the notifier writes them out, Markdown included."""

from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum

from catalog_matching.domain.decision_tier import DecisionTier
from p2pwatch.domain.observability.events import TargetTitle
from p2pwatch.domain.observability.severity import Severity
from p2pwatch.domain.source import SourceKey


@dataclass(frozen=True)
class TierRise:
    """A file's targets risen to ``tier``, the highest of them, ``ed2k_link`` fetching it."""

    tier: DecisionTier
    target_titles: tuple[TargetTitle, ...]
    filename: str
    size_bytes: int
    ed2k_link: str
    node_id: str


class SourceAlertKind(StrEnum):
    """Why a source is news, the value its metric label."""

    FIRST_USEFUL = "first_useful"
    REAPPEARED = "reappeared"


@dataclass(frozen=True)
class SourceAlert:
    """A source useful on a file, ``absent_for`` that long before, ``None`` for a first one."""

    kind: SourceAlertKind
    source: SourceKey
    source_name: str | None
    absent_for: timedelta | None
    target_titles: tuple[TargetTitle, ...]
    filename: str
    node_id: str


@dataclass(frozen=True)
class CompletedDownload:
    """A file the client finished downloading, with every download target it holds."""

    target_titles: tuple[TargetTitle, ...]
    filename: str
    node_id: str


@dataclass(frozen=True)
class RelayedLogLine:
    """An event's log line, relayed unchanged: it has no text of its own."""

    message: str
    severity: Severity
    node_id: str


type Notification = TierRise | SourceAlert | CompletedDownload | RelayedLogLine
