"""Observability policy: ``plan_observability(event) → ObservabilityPlan`` (spec Plan E §3, E-D3).

DOMAIN ring (pure). The ONLY place that decides, for each event, severity, message,
node metric(s), notification. ``plan_observability`` is an EXHAUSTIVE match (``assert_never`` →
100% branch).
The domain knows nothing of ``logging``, Prometheus or apprise: ``Severity``/``Audience``/
``NodeMetricName`` are DOMAIN enums, translated by the adapters (E-D3), and a community notification
is a typed value whose Markdown the notifier writes.
"""

from dataclasses import dataclass, replace
from datetime import timedelta
from enum import Enum
from typing import assert_never

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
from p2pwatch.domain.observability.node_metric import (
    CounterIncrement,
    GaugeSetting,
    NodeMetricName,
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


@dataclass(frozen=True)
class ObservabilityPlan:
    """What one event produces: severity + message + node metric(s) + notification.

    ``node_metrics`` is a TUPLE (one event can feed several node metrics:
    ``ChannelStatusSampled`` sets two gauges). ``notification`` is a community kind, or the log
    line relayed to the operations.
    """

    severity: Severity
    message: str
    node_metrics: tuple[CounterIncrement | GaugeSetting, ...] = ()
    notification: Notification | None = None


def audience_of(notification: Notification) -> Audience:
    """Who ``notification`` is for, which its kind decides."""
    match notification:
        case TierRise() | SourceAlert() | CompletedDownload():
            return Audience.COMMUNITY
        case RelayedLogLine():
            return Audience.OPERATIONS
        case _:  # pragma: no cover
            assert_never(notification)


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
    """How a log line and a node metric label name a decision."""
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
    name: NodeMetricName, event: ChannelStatusSampled, state: bool | None
) -> GaugeSetting:
    labels = (("client", event.client_name), ("channel", event.channel))
    if state is None:  # an unknown state has no series, never a stale one
        return GaugeSetting(name, labels, None)
    return GaugeSetting(name, labels, float(state))


def _relayed(
    severity: Severity,
    message: str,
    node_id: str,
    node_metrics: tuple[CounterIncrement | GaugeSetting, ...] = (),
) -> ObservabilityPlan:
    """An operations plan: its log line relayed under ``node_id``."""
    return ObservabilityPlan(
        severity, message, node_metrics, RelayedLogLine(message, severity, node_id)
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
            CounterIncrement(NodeMetricName.DECISIONS, (("tier", _label(c.new_decision)),))
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
        (CounterIncrement(NodeMetricName.SOURCE_ALERTS, labels),),
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
                    CounterIncrement(NodeMetricName.SEARCHES, _search_labels(event)),
                    # Even by 0: the series exists from the first search, before any drift.
                    CounterIncrement(
                        NodeMetricName.SEARCH_RESULTS_SKIPPED,
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
                    CounterIncrement(
                        NodeMetricName.CLIENT_UNREACHABLE, (("client", event.client_name),)
                    ),
                ),
            )
        case SearchFailed():
            return ObservabilityPlan(
                Severity.WARNING,
                f"search failed on {event.channel}",
                (CounterIncrement(NodeMetricName.SEARCH_FAILURES, _search_labels(event)),),
            )
        case ObservationRecorded():
            return ObservabilityPlan(
                Severity.DEBUG,
                f"observation recorded ({event.channel})",
                (CounterIncrement(NodeMetricName.OBSERVATIONS, _search_labels(event)),),
            )
        case DecisionsRecorded():
            return _plan_decisions(event)
        case DownloadQueued():
            return ObservabilityPlan(
                Severity.INFO,
                f"download queued: {event.target_id}",
                (CounterIncrement(NodeMetricName.DOWNLOADS_QUEUED),),
            )
        case DownloadCompleted():
            return ObservabilityPlan(
                Severity.SUCCESS,
                f"✅ download completed: {', '.join(t.target_id for t in event.target_titles)}",
                (CounterIncrement(NodeMetricName.DOWNLOADS_COMPLETED),),
                CompletedDownload(event.target_titles, event.filename, event.node_id),
            )
        case ChannelStatusSampled():
            return ObservabilityPlan(
                Severity.DEBUG,
                f"status {event.client_name} {event.channel}: "
                f"connected {_yes_no(event.connected)}, connectable {_yes_no(event.connectable)}",
                (
                    _channel_gauge(NodeMetricName.CHANNEL_CONNECTED, event, event.connected),
                    _channel_gauge(NodeMetricName.CHANNEL_CONNECTABLE, event, event.connectable),
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
                (GaugeSetting(NodeMetricName.DISK_FREE_BYTES, (), float(event.free_bytes)),),
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
                (GaugeSetting(NodeMetricName.CRAWLER_UP, (), 1.0),),
            )
        case _:  # pragma: no cover
            assert_never(event)
