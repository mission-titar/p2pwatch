"""Observability policy: ``plan_observability(event) → ObservabilityPlan`` (spec Plan E §3, E-D3).

DOMAIN ring (pure). The ONLY place that decides, for each event, severity, message,
node metric(s), notification. ``plan_observability`` is an EXHAUSTIVE match (``assert_never`` →
100% branch).
The domain knows nothing of ``logging``, Prometheus or apprise: ``Severity``/``Audience``/
``NodeCounter``/``NodeGauge`` are DOMAIN enums, translated by the adapters (E-D3), and a community
notification is a typed value whose Markdown the notifier writes.
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
from p2pwatch.domain.identifiers import NodeId
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
    ChannelLabels,
    ClientLabels,
    CounterIncrement,
    DecisionLabels,
    GaugeSetting,
    NodeCounter,
    NodeGauge,
    SourceAlertLabels,
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


@dataclass(kw_only=True, frozen=True)
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
    """How a log line names a decision."""
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


def _channel_labels(
    event: SearchExecuted | SearchFailed | ObservationRecorded | ChannelStatusSampled,
) -> ChannelLabels:
    return ChannelLabels(client_name=event.client_name, channel=event.channel)


def _decision_labels(decision: FileTargetDecision) -> DecisionLabels:
    return DecisionLabels(tier="retracted" if isinstance(decision, Retraction) else decision.tier)


def _channel_gauge(
    gauge: NodeGauge, *, event: ChannelStatusSampled, state: bool | None
) -> GaugeSetting:
    if state is None:  # an unknown state has no series, never a stale one
        return GaugeSetting(gauge=gauge, labels=_channel_labels(event), value=None)
    return GaugeSetting(gauge=gauge, labels=_channel_labels(event), value=float(state))


def _relayed(
    severity: Severity,
    *,
    message: str,
    node_id: NodeId,
    node_metrics: tuple[CounterIncrement | GaugeSetting, ...] = (),
) -> ObservabilityPlan:
    """An operations plan: its log line relayed under ``node_id``."""
    return ObservabilityPlan(
        severity=severity,
        message=message,
        node_metrics=node_metrics,
        notification=RelayedLogLine(message=message, severity=severity, node_id=node_id),
    )


def _channel_alert(
    severity: Severity, *, event: ChannelDegraded | ChannelRecovered, state_phrase: str
) -> ObservabilityPlan:
    return _relayed(
        severity,
        message=f"{event.client_name} {event.channel}: {state_phrase}",
        node_id=event.node_id,
    )


def _plan_decisions(event: DecisionsRecorded) -> ObservabilityPlan:
    changes = ", ".join(
        f"{c.target_id} {_label(c.previous_decision)} → {_label(c.new_decision)}"
        for c in event.changes
    )
    plan = ObservabilityPlan(
        severity=Severity.INFO,
        message=f"decisions for {event.filename} ({event.file.native_id}): {changes}",
        node_metrics=tuple(
            CounterIncrement(counter=NodeCounter.DECISIONS, labels=_decision_labels(c.new_decision))
            for c in event.changes
        ),
    )
    risen = [(c, tier) for c in event.changes if (tier := _risen_tier(c)) is not None]
    if not risen:
        return plan
    top = max((tier for _, tier in risen), key=lambda tier: tier.rank)
    match event.file.network:
        case Network.ED2K:
            link = build_ed2k_link(
                event.filename, size_bytes=event.size_bytes, native_id=event.file.native_id
            )
        case _:  # pragma: no cover
            assert_never(event.file.network)
    target_titles = tuple(TargetTitle(target_id=c.target_id, title=c.title) for c, _ in risen)
    return replace(
        plan,
        notification=TierRise(
            tier=top,
            target_titles=target_titles,
            filename=event.filename,
            size_bytes=event.size_bytes,
            ed2k_link=link,
            node_id=event.node_id,
        ),
    )


def _plan_source(
    event: SourceFirstUseful | SourceReappeared,
    *,
    kind: SourceAlertKind,
    absent_for: timedelta | None,
    state_phrase: str,
) -> ObservabilityPlan:
    short = f"{event.source.native_id[:8]}…"  # as the webui shortens a hash
    return ObservabilityPlan(
        severity=Severity.INFO,
        message=f"source {short} {state_phrase}: {event.filename}",
        node_metrics=(
            CounterIncrement(
                counter=NodeCounter.SOURCE_ALERTS,
                labels=SourceAlertLabels(network=event.source.network, kind=kind),
            ),
        ),
        notification=SourceAlert(
            kind=kind,
            source=event.source,
            source_name=event.source_name,
            absent_for=absent_for,
            target_titles=event.target_titles,
            filename=event.filename,
            node_id=event.node_id,
        ),
    )


def plan_observability(event: Event) -> ObservabilityPlan:
    """Map an event to its ``ObservabilityPlan`` (EXHAUSTIVE match → 100% branch); a
    notification carries its event's node."""
    match event:
        case SearchExecuted():
            return ObservabilityPlan(
                severity=Severity.DEBUG,
                message=f"search {event.channel}: {event.observation_count} observation(s)",
                node_metrics=(
                    CounterIncrement(counter=NodeCounter.SEARCHES, labels=_channel_labels(event)),
                    # Even by 0: the series exists from the first search, before any drift.
                    CounterIncrement(
                        counter=NodeCounter.SEARCH_RESULTS_SKIPPED,
                        labels=_channel_labels(event),
                        amount=float(event.skipped_result_count),
                    ),
                ),
            )
        case ClientUnreachable():
            return ObservabilityPlan(
                severity=Severity.WARNING,
                message=f"{event.client_name} unreachable",
                node_metrics=(
                    CounterIncrement(
                        counter=NodeCounter.CLIENT_UNREACHABLE,
                        labels=ClientLabels(client_name=event.client_name),
                    ),
                ),
            )
        case SearchFailed():
            return ObservabilityPlan(
                severity=Severity.WARNING,
                message=f"search failed on {event.channel}",
                node_metrics=(
                    CounterIncrement(
                        counter=NodeCounter.SEARCH_FAILURES, labels=_channel_labels(event)
                    ),
                ),
            )
        case ObservationRecorded():
            return ObservabilityPlan(
                severity=Severity.DEBUG,
                message=f"observation recorded ({event.channel})",
                node_metrics=(
                    CounterIncrement(
                        counter=NodeCounter.OBSERVATIONS, labels=_channel_labels(event)
                    ),
                ),
            )
        case DecisionsRecorded():
            return _plan_decisions(event)
        case DownloadQueued():
            return ObservabilityPlan(
                severity=Severity.INFO,
                message=f"download queued: {event.target_id}",
                node_metrics=(CounterIncrement(counter=NodeCounter.DOWNLOADS_QUEUED),),
            )
        case DownloadCompleted():
            return ObservabilityPlan(
                severity=Severity.SUCCESS,
                message="✅ download completed: "
                + (", ".join(t.target_id for t in event.target_titles) or "unknown"),
                node_metrics=(CounterIncrement(counter=NodeCounter.DOWNLOADS_COMPLETED),),
                notification=CompletedDownload(
                    target_titles=event.target_titles,
                    filename=event.filename,
                    node_id=event.node_id,
                ),
            )
        case ChannelStatusSampled():
            return ObservabilityPlan(
                severity=Severity.DEBUG,
                message=f"status {event.client_name} {event.channel}: "
                f"connected {_yes_no(event.connected)}, connectable {_yes_no(event.connectable)}",
                node_metrics=(
                    _channel_gauge(NodeGauge.CHANNEL_CONNECTED, event=event, state=event.connected),
                    _channel_gauge(
                        NodeGauge.CHANNEL_CONNECTABLE, event=event, state=event.connectable
                    ),
                ),
            )
        case ChannelDegraded():
            return _channel_alert(
                Severity.WARNING,
                event=event,
                state_phrase=f"{_DEGRADED_PHRASE_BY_FIELD[event.field]} "
                f"for {event.degraded_for_seconds / 60:.0f} min",
            )
        case ChannelRecovered():
            return _channel_alert(
                Severity.INFO, event=event, state_phrase=_RECOVERED_PHRASE_BY_FIELD[event.field]
            )
        case ClientUnreachableLasting():
            return _relayed(
                Severity.WARNING,
                message=f"{event.client_name} unreachable "
                f"for {event.unreachable_for_seconds / 60:.0f} min",
                node_id=event.node_id,
            )
        case ClientReachableAgain():
            return _relayed(
                Severity.INFO, message=f"{event.client_name} reachable again", node_id=event.node_id
            )
        case FreeSpaceSampled():
            return ObservabilityPlan(
                severity=Severity.DEBUG,
                message=f"download disk free: {event.free_bytes} bytes",
                node_metrics=(
                    GaugeSetting(
                        gauge=NodeGauge.DISK_FREE_BYTES, labels=None, value=float(event.free_bytes)
                    ),
                ),
            )
        case DiskSpaceLow():
            return _relayed(
                Severity.WARNING,
                message=f"download disk low: {event.free_bytes / 2**30:.1f} GiB free, "
                f"under the {event.min_free_bytes / 2**30:.1f} GiB floor (no new download)",
                node_id=event.node_id,
            )
        case SourceFirstUseful():
            return _plan_source(
                event,
                kind=SourceAlertKind.FIRST_USEFUL,
                absent_for=None,
                state_phrase="useful for the first time",
            )
        case SourceReappeared():
            return _plan_source(
                event,
                kind=SourceAlertKind.REAPPEARED,
                absent_for=timedelta(seconds=event.absent_for_seconds),
                state_phrase=f"reappeared after {event.absent_for_seconds / 3600:.0f} h",
            )
        case CrawlerStarted():
            return _relayed(
                Severity.INFO,
                message=f"🟢 node online (download {'on' if event.download_enabled else 'off'})",
                node_id=event.node_id,
                node_metrics=(GaugeSetting(gauge=NodeGauge.CRAWLER_UP, labels=None, value=1.0),),
            )
        case _:  # pragma: no cover
            assert_never(event)
