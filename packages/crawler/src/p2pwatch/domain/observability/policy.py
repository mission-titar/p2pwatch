"""Observability policy: ``describe(event) → Report`` (spec Plan E §3, E-D3).

DOMAIN layer (pure). The ONLY place that decides, for each event, severity, message,
metric(s), audiences. ``describe`` is an EXHAUSTIVE match (``assert_never`` → 100% branch).
The domain knows nothing of ``logging``, Prometheus or apprise: ``Severity``/``Audience``/
``MetricName`` are DOMAIN enums, translated by the adapters (E-D3).

Prometheus GOTCHA: COUNTER names do NOT include ``_total`` here: ``prometheus_client``
adds it at exposition (including it would produce ``…_total_total``). Gauges: name
as-is.
"""

from collections.abc import Iterable
from dataclasses import dataclass, replace
from enum import Enum, StrEnum, auto
from typing import Literal, assert_never

from catalog_matching.config import TIER_RANK
from catalog_matching.ed2k_link import build_ed2k_link
from p2pwatch.domain.file_key import Network
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


class Severity(Enum):
    """DOMAIN severity of a fact (translated to a ``logging`` level by the adapter)."""

    DEBUG = auto()
    INFO = auto()
    SUCCESS = auto()
    WARNING = auto()
    ERROR = auto()


class Audience(Enum):
    """Consumer of a notification (E-D7): the VALUE is the apprise tag."""

    COMMUNITY = "community"
    OPERATIONS = "operations"


class MetricName(StrEnum):
    """Metric names. Counters WITHOUT ``_total`` (added by prometheus_client at exposition)."""

    SEARCHES = "p2pwatch_searches"
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


MetricKind = Literal["inc", "set", "remove"]


@dataclass(frozen=True)
class MetricInstruction:
    """A metric operation: counter ``inc`` / gauge ``set`` or ``remove``.

    ``labels`` = tuple of ordered (key, value) pairs (hashable → usable in a ``Report``
    equality test). ``value`` = quantity (default 1.0 for ``inc``).
    """

    name: MetricName
    kind: MetricKind
    labels: tuple[tuple[str, str], ...] = ()
    value: float = 1.0


@dataclass(frozen=True)
class Report:
    """How to report an event: severity + message + metric(s) + notif audiences.

    ``metrics`` is a TUPLE (one event can feed several metrics: ``ChannelStatusSampled`` sets
    two gauges). Empty ``audiences`` = no notif.
    ``notification`` is the notified body when it differs from the logged ``message``; ``title``
    heads it.
    """

    severity: Severity
    message: str
    metrics: tuple[MetricInstruction, ...] = ()
    audiences: frozenset[Audience] = frozenset()
    notification: str = ""
    title: str = ""


# The tiers a rise announces, with the heading of the message.
_RISE_HEADINGS = {"download": "📥 Download", "notify": "🔎 Notify"}


def _rank(tier: str | None) -> int:
    """``TIER_RANK``, where none and ``retracted`` rank below every tier."""
    return TIER_RANK.get(tier or "", -1)


def _is_rise(change: DecisionChange) -> bool:
    new_tier, previous_tier = change.new_tier, change.previous_tier
    return new_tier in _RISE_HEADINGS and _rank(new_tier) > _rank(previous_tier)


def _targets_section(target_titles: Iterable[TargetTitle]) -> str:
    return "**Targets**\n" + "\n".join(f"{t.target_id} - {t.title}" for t in target_titles)


def _code_name(filename: str) -> str:
    # A backtick would close the span and let the rest of the name read as markup.
    return "`" + filename.replace("`", "'") + "`"


_DEGRADED: dict[ChannelField, str] = {
    "connected": "off its network",
    "connectable": "not connectable",
}
_RECOVERED: dict[ChannelField, str] = {
    "connected": "back on its network",
    "connectable": "connectable again",
}


def _word(value: bool | None) -> str:
    return "unknown" if value is None else "yes" if value else "no"


def _search_labels(
    event: SearchExecuted | SearchFailed | ObservationRecorded,
) -> tuple[tuple[str, str], ...]:
    return (("client", event.client_name), ("channel", event.channel))


def _channel_gauge(
    name: MetricName, event: ChannelStatusSampled, value: bool | None
) -> MetricInstruction:
    labels = (("client", event.client_name), ("channel", event.channel))
    if value is None:  # an unknown state has no series, never a stale one
        return MetricInstruction(name, "remove", labels)
    return MetricInstruction(name, "set", labels, float(value))


def _channel_alert(
    severity: Severity, event: ChannelDegraded | ChannelRecovered, what: str
) -> Report:
    return Report(
        severity,
        f"{event.client_name} {event.channel}: {what}",
        (),
        frozenset({Audience.OPERATIONS}),
    )


def _describe_decisions(event: DecisionsRecorded) -> Report:
    changes = ", ".join(
        f"{c.target_id} {c.previous_tier or 'none'} → {c.new_tier}" for c in event.changes
    )
    report = Report(
        Severity.INFO,
        f"decisions for {event.filename} ({event.file.native_id}): {changes}",
        tuple(
            MetricInstruction(MetricName.DECISIONS, "inc", (("tier", c.new_tier),))
            for c in event.changes
        ),
    )
    risen = [c for c in event.changes if _is_rise(c)]
    if not risen:
        return report
    top = max((c.new_tier for c in risen), key=_rank)
    match event.file.network:
        case Network.ED2K:
            link = build_ed2k_link(event.filename, event.size_bytes, event.file.native_id)
        case _:  # pragma: no cover
            assert_never(event.file.network)
    return replace(
        report,
        audiences=frozenset({Audience.COMMUNITY}),
        notification=(
            _targets_section(TargetTitle(c.target_id, c.title) for c in risen)
            + f"\n\n**File**\n{event.size_bytes / 2**20:.1f} MiB - {_code_name(event.filename)}"
            + f"\n\n**ed2k**\n`{link}`"
        ),
        title=_RISE_HEADINGS[top],
    )


def _describe_source(
    event: SourceFirstUseful | SourceReappeared, kind: str, what: str, title: str
) -> Report:
    short = f"{event.source.native_id[:8]}…"  # as the webui shortens a hash
    named = f"{_code_name(event.source_name)} " if event.source_name else ""
    sections = [f"**Source**\n{named}{short}, {what}"]
    if event.target_titles:
        sections.append(_targets_section(event.target_titles))
    sections.append(f"**File**\n{_code_name(event.filename)}")
    labels = (("network", event.source.network.value), ("kind", kind))
    return Report(
        Severity.INFO,
        f"source {short} {what}: {event.filename}",
        (MetricInstruction(MetricName.SOURCE_ALERTS, "inc", labels),),
        frozenset({Audience.COMMUNITY}),
        "\n\n".join(sections),
        title,
    )


def describe(event: Event) -> Report:
    """Map an event to its ``Report`` (EXHAUSTIVE match → 100% branch)."""
    match event:
        case SearchExecuted():
            return Report(
                Severity.DEBUG,
                f"search {event.channel}: {event.result_count} result(s)",
                (MetricInstruction(MetricName.SEARCHES, "inc", _search_labels(event)),),
            )
        case ClientUnreachable():
            return Report(
                Severity.WARNING,
                f"{event.client_name} unreachable",
                (
                    MetricInstruction(
                        MetricName.CLIENT_UNREACHABLE, "inc", (("client", event.client_name),)
                    ),
                ),
            )
        case SearchFailed():
            return Report(
                Severity.WARNING,
                f"search failed on {event.channel}",
                (MetricInstruction(MetricName.SEARCH_FAILURES, "inc", _search_labels(event)),),
            )
        case ObservationRecorded():
            return Report(
                Severity.DEBUG,
                f"observation recorded ({event.channel})",
                (MetricInstruction(MetricName.OBSERVATIONS, "inc", _search_labels(event)),),
            )
        case DecisionsRecorded():
            return _describe_decisions(event)
        case DownloadQueued():
            return Report(
                Severity.INFO,
                f"download queued: {event.target_id}",
                (MetricInstruction(MetricName.DOWNLOADS_QUEUED, "inc"),),
            )
        case DownloadCompleted():
            return Report(
                Severity.SUCCESS,
                f"✅ download completed: {', '.join(t.target_id for t in event.target_titles)}",
                (MetricInstruction(MetricName.DOWNLOADS_COMPLETED, "inc"),),
                frozenset({Audience.COMMUNITY}),
                _targets_section(event.target_titles)
                + f"\n\n**File**\n{_code_name(event.filename)}",
                "✅ Downloaded",
            )
        case ChannelStatusSampled():
            return Report(
                Severity.DEBUG,
                f"status {event.client_name} {event.channel}: connected {_word(event.connected)}, "
                f"connectable {_word(event.connectable)}",
                (
                    _channel_gauge(MetricName.CHANNEL_CONNECTED, event, event.connected),
                    _channel_gauge(MetricName.CHANNEL_CONNECTABLE, event, event.connectable),
                ),
            )
        case ChannelDegraded():
            return _channel_alert(
                Severity.WARNING,
                event,
                f"{_DEGRADED[event.field]} for {event.seconds / 60:.0f} min",
            )
        case ChannelRecovered():
            return _channel_alert(Severity.INFO, event, _RECOVERED[event.field])
        case ClientUnreachableLasting():
            return Report(
                Severity.WARNING,
                f"{event.client_name} unreachable for {event.seconds / 60:.0f} min",
                (),
                frozenset({Audience.OPERATIONS}),
            )
        case ClientReachableAgain():
            return Report(
                Severity.INFO,
                f"{event.client_name} reachable again",
                (),
                frozenset({Audience.OPERATIONS}),
            )
        case FreeSpaceSampled():
            return Report(
                Severity.DEBUG,
                f"download disk free: {event.free_bytes} bytes",
                (
                    MetricInstruction(
                        MetricName.DISK_FREE_BYTES, "set", (), float(event.free_bytes)
                    ),
                ),
            )
        case DiskSpaceLow():
            return Report(
                Severity.WARNING,
                f"download disk low: {event.free_bytes / 2**30:.1f} GiB free, "
                f"under the {event.min_free_bytes / 2**30:.1f} GiB floor (no new download)",
                (),
                frozenset({Audience.OPERATIONS}),
            )
        case SourceFirstUseful():
            return _describe_source(
                event,
                "first_useful",
                "useful for the first time",
                "🆕 Source useful for the first time",
            )
        case SourceReappeared():
            return _describe_source(
                event,
                "reappeared",
                f"reappeared after {event.absent_seconds / 3600:.0f} h",
                "🔁 Source reappeared",
            )
        case CrawlerStarted():
            return Report(
                Severity.INFO,
                f"🟢 node online (download {'on' if event.download_enabled else 'off'})",
                (MetricInstruction(MetricName.CRAWLER_UP, "set", (), 1.0),),
                frozenset({Audience.OPERATIONS}),
            )
        case _:  # pragma: no cover
            assert_never(event)
