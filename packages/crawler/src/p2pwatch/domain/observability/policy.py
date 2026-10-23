"""Observability policy: ``plan_observability(event) → ObservabilityPlan`` (spec Plan E §3, E-D3).

DOMAIN ring (pure). The ONLY place that decides, for each event, severity, message,
metric(s), audiences. ``plan_observability`` is an EXHAUSTIVE match (``assert_never`` → 100%
branch).
The domain knows nothing of ``logging``, Prometheus or apprise: ``Severity``/``Audience``/
``MetricName`` are DOMAIN enums, translated by the adapters (E-D3), and a community notification
is a typed value whose Markdown the notifier writes.

Prometheus GOTCHA: COUNTER names do NOT include ``_total`` here: ``prometheus_client``
adds it at exposition (including it would produce ``…_total_total``). Gauges: name
as-is.
"""

from dataclasses import dataclass, replace
from datetime import timedelta
from enum import Enum, StrEnum
from typing import Literal, assert_never

from catalog_matching.domain.decision_tier import DecisionTier
from catalog_matching.domain.ed2k_link import build_ed2k_link
from catalog_matching.domain.engine import DecisionRecord
from p2pwatch.domain.file_key import Network
from p2pwatch.domain.file_target_decision import FileTargetDecision, Retraction
from p2pwatch.domain.observability.events import (
    ChannelDegraded,
    ChannelField,
    ChannelRecovered,
    ChannelStatusSampled,
    ClientReachableAgain,
    ClientUnreachable,
    ClientUnreachableLasting,
    CrawlerStarted,
    DecisionChange,
    DecisionsRecorded,
    DiskSpaceLow,
    DownloadCompleted,
    DownloadQueued,
    Event,
    FreeSpaceSampled,
    ObservationRecorded,
    SearchExecuted,
    SearchFailed,
    SourceFirstUseful,
    SourceReappeared,
    TargetTitle,
)
from p2pwatch.domain.observability.notification import (
    CompletedDownload,
    Notification,
    RelayedLogLine,
    SourceAlert,
    SourceAlertKind,
    TierRise,
)
from p2pwatch.domain.observability.severity import Severity


class Audience(Enum):
    """Consumer of a notification (E-D7): the VALUE is the apprise tag."""

    COMMUNITY = "community"
    OPERATIONS = "operations"


class MetricName(StrEnum):
    """Metric names. Counters WITHOUT ``_total`` (added by prometheus_client at exposition)."""

    SEARCHES = "p2pwatch_searches"
    SEARCH_RESULTS_SKIPPED = "p2pwatch_search_results_skipped"
    OBSERVATIONS = "p2pwatch_observations"
    SEARCH_FAILURES = "p2pwatch_search_failures"
    CLIENT_UNREACHABLE = "p2pwatch_client_unreachable"
    DECISIONS = "p2pwatch_decisions"
    DOWNLOADS_QUEUED = "p2pwatch_downloads_queued"
    DOWNLOADS_COMPLETED = "p2pwatch_downloads_completed"
    DISK_FREE_BYTES = "p2pwatch_download_disk_free_bytes"
    CRAWLER_UP = "p2pwatch_crawler_up"
    CHANNEL_CONNECTED = "p2pwatch_channel_connected"
    CHANNEL_CONNECTABLE = "p2pwatch_channel_connectable"
    SOURCE_ALERTS = "p2pwatch_source_alerts"


MetricOperation = Literal["inc", "set", "remove"]


@dataclass(frozen=True)
class MetricInstruction:
    """A metric operation: counter ``inc`` / gauge ``set`` or ``remove``.

    ``labels`` = tuple of ordered (key, value) pairs (hashable → usable in an ``ObservabilityPlan``
    equality test). ``amount`` = quantity (default 1.0 for ``inc``).
    """

    name: MetricName
    operation: MetricOperation
    labels: tuple[tuple[str, str], ...] = ()
    amount: float = 1.0


@dataclass(frozen=True)
class ObservabilityPlan:
    """What one event produces: severity + message + metric(s) + notification audiences.

    ``metrics`` is a TUPLE (one event can feed several metrics: ``ChannelStatusSampled`` sets
    two gauges). Empty ``audiences`` = no notification. ``notification`` is what each audience is
    sent: a community kind, or the log line relayed to the operations.
    """

    severity: Severity
    message: str
    metrics: tuple[MetricInstruction, ...] = ()
    audiences: frozenset[Audience] = frozenset()
    notification: Notification | None = None


def _rank(decision: FileTargetDecision | None) -> int:
    """``DecisionTier.rank``, where none and a retraction rank below every tier."""
    return decision.tier.rank if isinstance(decision, DecisionRecord) else -1


def _risen_tier(change: DecisionChange) -> DecisionTier | None:
    """The tier ``change`` rises to, if it announces one."""
    new = change.new_decision
    if not isinstance(new, DecisionRecord) or not new.tier.identifies_target:
        return None
    return new.tier if new.tier.rank > _rank(change.previous_decision) else None


def _label(decision: FileTargetDecision | None) -> str:
    """How a log line and a metric label name a decision."""
    if decision is None:
        return "none"
    if isinstance(decision, Retraction):
        return "retracted"
    return decision.tier


_DEGRADED_PHRASE_BY_FIELD: dict[ChannelField, str] = {
    "connected": "off its network",
    "connectable": "not connectable",
}
_RECOVERED_PHRASE_BY_FIELD: dict[ChannelField, str] = {
    "connected": "back on its network",
    "connectable": "connectable again",
}


def _yes_no(flag: bool | None) -> str:
    return "unknown" if flag is None else "yes" if flag else "no"


def _search_labels(
    event: SearchExecuted | SearchFailed | ObservationRecorded,
) -> tuple[tuple[str, str], ...]:
    return (("client", event.client_name), ("channel", event.channel))


def _channel_gauge(
    name: MetricName, event: ChannelStatusSampled, state: bool | None
) -> MetricInstruction:
    labels = (("client", event.client_name), ("channel", event.channel))
    if state is None:  # an unknown state has no series, never a stale one
        return MetricInstruction(name, "remove", labels)
    return MetricInstruction(name, "set", labels, float(state))


def _relayed(
    severity: Severity, message: str, node_id: str, metrics: tuple[MetricInstruction, ...] = ()
) -> ObservabilityPlan:
    """An operations plan: its log line relayed under ``node_id``."""
    return ObservabilityPlan(
        severity,
        message,
        metrics,
        frozenset({Audience.OPERATIONS}),
        RelayedLogLine(message, severity, node_id),
    )


def _channel_alert(
    severity: Severity, event: ChannelDegraded | ChannelRecovered, state_phrase: str
) -> ObservabilityPlan:
    return _relayed(severity, f"{event.client_name} {event.channel}: {state_phrase}", event.node_id)


def _plan_decisions(event: DecisionsRecorded) -> ObservabilityPlan:
    changes = ", ".join(
        f"{c.target_id} {_label(c.previous_decision)} → {_label(c.new_decision)}"
        for c in event.changes
    )
    plan = ObservabilityPlan(
        Severity.INFO,
        f"decisions for {event.filename} ({event.file.native_id}): {changes}",
        tuple(
            MetricInstruction(MetricName.DECISIONS, "inc", (("tier", _label(c.new_decision)),))
            for c in event.changes
        ),
    )
    risen = [(c, tier) for c in event.changes if (tier := _risen_tier(c)) is not None]
    if not risen:
        return plan
    top = max((tier for _, tier in risen), key=lambda tier: tier.rank)
    match event.file.network:
        case Network.ED2K:
            link = build_ed2k_link(event.filename, event.size_bytes, event.file.native_id)
        case _:  # pragma: no cover
            assert_never(event.file.network)
    target_titles = tuple(TargetTitle(c.target_id, c.title) for c, _ in risen)
    return replace(
        plan,
        audiences=frozenset({Audience.COMMUNITY}),
        notification=TierRise(
            top, target_titles, event.filename, event.size_bytes, link, event.node_id
        ),
    )


def _plan_source(
    event: SourceFirstUseful | SourceReappeared,
    kind: SourceAlertKind,
    absent_for: timedelta | None,
    state_phrase: str,
) -> ObservabilityPlan:
    short = f"{event.source.native_id[:8]}…"  # as the webui shortens a hash
    labels = (("network", event.source.network.value), ("kind", kind.value))
    return ObservabilityPlan(
        Severity.INFO,
        f"source {short} {state_phrase}: {event.filename}",
        (MetricInstruction(MetricName.SOURCE_ALERTS, "inc", labels),),
        frozenset({Audience.COMMUNITY}),
        SourceAlert(
            kind,
            event.source,
            event.source_name,
            absent_for,
            event.target_titles,
            event.filename,
            event.node_id,
        ),
    )


def plan_observability(event: Event) -> ObservabilityPlan:
    """Map an event to its ``ObservabilityPlan`` (EXHAUSTIVE match → 100% branch); a
    notification carries its event's node."""
    match event:
        case SearchExecuted():
            return ObservabilityPlan(
                Severity.DEBUG,
                f"search {event.channel}: {event.observation_count} observation(s)",
                (
                    MetricInstruction(MetricName.SEARCHES, "inc", _search_labels(event)),
                    # Even by 0: the series exists from the first search, before any drift.
                    MetricInstruction(
                        MetricName.SEARCH_RESULTS_SKIPPED,
                        "inc",
                        _search_labels(event),
                        float(event.skipped_result_count),
                    ),
                ),
            )
        case ClientUnreachable():
            return ObservabilityPlan(
                Severity.WARNING,
                f"{event.client_name} unreachable",
                (
                    MetricInstruction(
                        MetricName.CLIENT_UNREACHABLE, "inc", (("client", event.client_name),)
                    ),
                ),
            )
        case SearchFailed():
            return ObservabilityPlan(
                Severity.WARNING,
                f"search failed on {event.channel}",
                (MetricInstruction(MetricName.SEARCH_FAILURES, "inc", _search_labels(event)),),
            )
        case ObservationRecorded():
            return ObservabilityPlan(
                Severity.DEBUG,
                f"observation recorded ({event.channel})",
                (MetricInstruction(MetricName.OBSERVATIONS, "inc", _search_labels(event)),),
            )
        case DecisionsRecorded():
            return _plan_decisions(event)
        case DownloadQueued():
            return ObservabilityPlan(
                Severity.INFO,
                f"download queued: {event.target_id}",
                (MetricInstruction(MetricName.DOWNLOADS_QUEUED, "inc"),),
            )
        case DownloadCompleted():
            return ObservabilityPlan(
                Severity.SUCCESS,
                f"✅ download completed: {', '.join(t.target_id for t in event.target_titles)}",
                (MetricInstruction(MetricName.DOWNLOADS_COMPLETED, "inc"),),
                frozenset({Audience.COMMUNITY}),
                CompletedDownload(event.target_titles, event.filename, event.node_id),
            )
        case ChannelStatusSampled():
            return ObservabilityPlan(
                Severity.DEBUG,
                f"status {event.client_name} {event.channel}: "
                f"connected {_yes_no(event.connected)}, connectable {_yes_no(event.connectable)}",
                (
                    _channel_gauge(MetricName.CHANNEL_CONNECTED, event, event.connected),
                    _channel_gauge(MetricName.CHANNEL_CONNECTABLE, event, event.connectable),
                ),
            )
        case ChannelDegraded():
            return _channel_alert(
                Severity.WARNING,
                event,
                f"{_DEGRADED_PHRASE_BY_FIELD[event.field]} "
                f"for {event.degraded_for_seconds / 60:.0f} min",
            )
        case ChannelRecovered():
            return _channel_alert(Severity.INFO, event, _RECOVERED_PHRASE_BY_FIELD[event.field])
        case ClientUnreachableLasting():
            return _relayed(
                Severity.WARNING,
                f"{event.client_name} unreachable for {event.unreachable_for_seconds / 60:.0f} min",
                event.node_id,
            )
        case ClientReachableAgain():
            return _relayed(Severity.INFO, f"{event.client_name} reachable again", event.node_id)
        case FreeSpaceSampled():
            return ObservabilityPlan(
                Severity.DEBUG,
                f"download disk free: {event.free_bytes} bytes",
                (
                    MetricInstruction(
                        MetricName.DISK_FREE_BYTES, "set", (), float(event.free_bytes)
                    ),
                ),
            )
        case DiskSpaceLow():
            return _relayed(
                Severity.WARNING,
                f"download disk low: {event.free_bytes / 2**30:.1f} GiB free, "
                f"under the {event.min_free_bytes / 2**30:.1f} GiB floor (no new download)",
                event.node_id,
            )
        case SourceFirstUseful():
            return _plan_source(
                event, SourceAlertKind.FIRST_USEFUL, None, "useful for the first time"
            )
        case SourceReappeared():
            return _plan_source(
                event,
                SourceAlertKind.REAPPEARED,
                timedelta(seconds=event.absent_for_seconds),
                f"reappeared after {event.absent_for_seconds / 3600:.0f} h",
            )
        case CrawlerStarted():
            return _relayed(
                Severity.INFO,
                f"🟢 node online (download {'on' if event.download_enabled else 'off'})",
                event.node_id,
                (MetricInstruction(MetricName.CRAWLER_UP, "set", (), 1.0),),
            )
        case _:  # pragma: no cover
            assert_never(event)
