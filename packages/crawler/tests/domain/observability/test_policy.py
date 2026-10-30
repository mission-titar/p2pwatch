"""``plan_observability`` is an exhaustive match: one case per event + each conditional branch
(a rise or not, first_occurrence true/false)."""

from datetime import timedelta

import pytest

from catalog_matching.domain.decision_tier import DecisionTier
from catalog_matching.domain.engine import DecisionRecord
from catalog_matching.domain.identifiers import TargetId
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.file_target_decision import FileTargetDecision, Retraction
from p2pwatch.domain.identifiers import Channel, ClientName, NodeId
from p2pwatch.domain.observability import events as ev
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
from p2pwatch.domain.observability.policy import (
    Audience,
    ObservabilityPlan,
    audience_of,
    plan_observability,
)
from p2pwatch.domain.observability.severity import Severity
from p2pwatch.domain.source import SourceKey

_AMULED_KAD = ChannelLabels(client_name=ClientName("amuled"), channel=Channel("kad"))
_AMULED_ED2K = ChannelLabels(client_name=ClientName("amuled"), channel=Channel("ed2k"))
_ED2K_FIRST_USEFUL = SourceAlertLabels(network=Network.ED2K, kind=SourceAlertKind.FIRST_USEFUL)
_ED2K_REAPPEARED = SourceAlertLabels(network=Network.ED2K, kind=SourceAlertKind.REAPPEARED)
_SOURCE = SourceKey(network=Network.ED2K, native_id="1f2e3d4c" * 4)
_FILE = FileKey(network=Network.ED2K, native_id="8f3a1c0b9e7d44a2b6c1f0e9d8a7b6c5")
_062A = (ev.TargetTitle(target_id=TargetId("062A"), title="Les demoiselles cambrioleuses"),)
_NODE_ID = NodeId("titar-node-1")


def _relayed(
    severity: Severity,
    *,
    message: str,
    node_metrics: tuple[CounterIncrement | GaugeSetting, ...] = (),
) -> ObservabilityPlan:
    """An operations plan: its log line relayed under the event's node."""
    return ObservabilityPlan(
        severity=severity,
        message=message,
        node_metrics=node_metrics,
        notification=RelayedLogLine(message=message, severity=severity, node_id=_NODE_ID),
    )


CASES: list[tuple[ev.Event, ObservabilityPlan]] = [
    (
        ev.SearchExecuted(
            client_name=ClientName("amuled"),
            channel=Channel("ed2k"),
            observation_count=7,
            skipped_result_count=2,
        ),
        ObservabilityPlan(
            severity=Severity.DEBUG,
            message="search ed2k: 7 observation(s)",
            node_metrics=(
                CounterIncrement(counter=NodeCounter.SEARCHES, labels=_AMULED_ED2K),
                CounterIncrement(
                    counter=NodeCounter.SEARCH_RESULTS_SKIPPED, labels=_AMULED_ED2K, amount=2.0
                ),
            ),
        ),
    ),
    (
        ev.ClientUnreachable(client_name=ClientName("slskd")),
        ObservabilityPlan(
            severity=Severity.WARNING,
            message="slskd unreachable",
            node_metrics=(
                CounterIncrement(
                    counter=NodeCounter.CLIENT_UNREACHABLE,
                    labels=ClientLabels(client_name=ClientName("slskd")),
                ),
            ),
        ),
    ),
    (
        ev.SearchFailed(client_name=ClientName("amuled"), channel=Channel("kad")),
        ObservabilityPlan(
            severity=Severity.WARNING,
            message="search failed on kad",
            node_metrics=(
                CounterIncrement(counter=NodeCounter.SEARCH_FAILURES, labels=_AMULED_KAD),
            ),
        ),
    ),
    (
        ev.ObservationRecorded(client_name=ClientName("amuled"), channel=Channel("kad")),
        ObservabilityPlan(
            severity=Severity.DEBUG,
            message="observation recorded (kad)",
            node_metrics=(CounterIncrement(counter=NodeCounter.OBSERVATIONS, labels=_AMULED_KAD),),
        ),
    ),
    (
        ev.DownloadQueued(target_id=TargetId("062A")),
        ObservabilityPlan(
            severity=Severity.INFO,
            message="download queued: 062A",
            node_metrics=(CounterIncrement(counter=NodeCounter.DOWNLOADS_QUEUED),),
        ),
    ),
    (
        ev.ChannelStatusSampled(
            client_name=ClientName("amuled"),
            channel=Channel("kad"),
            connected=True,
            connectable=False,
        ),
        ObservabilityPlan(
            severity=Severity.DEBUG,
            message="status amuled kad: connected yes, connectable no",
            node_metrics=(
                GaugeSetting(gauge=NodeGauge.CHANNEL_CONNECTED, labels=_AMULED_KAD, value=1.0),
                GaugeSetting(gauge=NodeGauge.CHANNEL_CONNECTABLE, labels=_AMULED_KAD, value=0.0),
            ),
        ),
    ),
    (
        ev.ChannelStatusSampled(
            client_name=ClientName("amuled"),
            channel=Channel("kad"),
            connected=None,
            connectable=None,
        ),
        ObservabilityPlan(
            severity=Severity.DEBUG,
            message="status amuled kad: connected unknown, connectable unknown",
            node_metrics=(
                GaugeSetting(gauge=NodeGauge.CHANNEL_CONNECTED, labels=_AMULED_KAD, value=None),
                GaugeSetting(gauge=NodeGauge.CHANNEL_CONNECTABLE, labels=_AMULED_KAD, value=None),
            ),
        ),
    ),
    (
        ev.ChannelDegraded(
            client_name=ClientName("amuled"),
            channel=Channel("ed2k"),
            field="connected",
            degraded_for_seconds=300.0,
            node_id=_NODE_ID,
        ),
        _relayed(Severity.WARNING, message="amuled ed2k: off its network for 5 min"),
    ),
    (
        ev.ChannelDegraded(
            client_name=ClientName("amuled"),
            channel=Channel("kad"),
            field="connectable",
            degraded_for_seconds=300.0,
            node_id=_NODE_ID,
        ),
        _relayed(Severity.WARNING, message="amuled kad: not connectable for 5 min"),
    ),
    (
        ev.ChannelRecovered(
            client_name=ClientName("amuled"),
            channel=Channel("ed2k"),
            field="connected",
            node_id=_NODE_ID,
        ),
        _relayed(Severity.INFO, message="amuled ed2k: back on its network"),
    ),
    (
        ev.ChannelRecovered(
            client_name=ClientName("amuled"),
            channel=Channel("kad"),
            field="connectable",
            node_id=_NODE_ID,
        ),
        _relayed(Severity.INFO, message="amuled kad: connectable again"),
    ),
    (
        ev.ClientUnreachableLasting(
            client_name=ClientName("amuled"), unreachable_for_seconds=120.0, node_id=_NODE_ID
        ),
        _relayed(Severity.WARNING, message="amuled unreachable for 2 min"),
    ),
    (
        ev.ClientReachableAgain(client_name=ClientName("amuled"), node_id=_NODE_ID),
        _relayed(Severity.INFO, message="amuled reachable again"),
    ),
    (
        ev.FreeSpaceSampled(free_bytes=5_000),
        ObservabilityPlan(
            severity=Severity.DEBUG,
            message="download disk free: 5000 bytes",
            node_metrics=(
                GaugeSetting(gauge=NodeGauge.DISK_FREE_BYTES, labels=None, value=5_000.0),
            ),
        ),
    ),
    (
        ev.DiskSpaceLow(free_bytes=3 * 2**29, min_free_bytes=10 * 2**30, node_id=_NODE_ID),
        _relayed(
            Severity.WARNING,
            message="download disk low: 1.5 GiB free, under the 10.0 GiB floor (no new download)",
        ),
    ),
    (
        ev.CrawlerStarted(download_enabled=True, node_id=_NODE_ID),
        _relayed(
            Severity.INFO,
            message="🟢 node online (download on)",
            node_metrics=(GaugeSetting(gauge=NodeGauge.CRAWLER_UP, labels=None, value=1.0),),
        ),
    ),
    (
        ev.CrawlerStarted(download_enabled=False, node_id=_NODE_ID),
        _relayed(
            Severity.INFO,
            message="🟢 node online (download off)",
            node_metrics=(GaugeSetting(gauge=NodeGauge.CRAWLER_UP, labels=None, value=1.0),),
        ),
    ),
    (
        ev.SourceFirstUseful(
            source=_SOURCE,
            source_name="AnimuseeFMR",
            file=_FILE,
            filename="Keroro 062.avi",
            target_titles=_062A,
            node_id=_NODE_ID,
        ),
        ObservabilityPlan(
            severity=Severity.INFO,
            message="source 1f2e3d4c… useful for the first time: Keroro 062.avi",
            node_metrics=(
                CounterIncrement(counter=NodeCounter.SOURCE_ALERTS, labels=_ED2K_FIRST_USEFUL),
            ),
            notification=SourceAlert(
                kind=SourceAlertKind.FIRST_USEFUL,
                source=_SOURCE,
                source_name="AnimuseeFMR",
                absent_for=None,
                target_titles=_062A,
                filename="Keroro 062.avi",
                node_id=_NODE_ID,
            ),
        ),
    ),
    (
        ev.SourceReappeared(
            source=_SOURCE,
            source_name="AnimuseeFMR",
            file=_FILE,
            filename="Keroro 062.avi",
            target_titles=_062A,
            absent_for_seconds=93_600.0,
            node_id=_NODE_ID,
        ),
        ObservabilityPlan(
            severity=Severity.INFO,
            message="source 1f2e3d4c… reappeared after 26 h: Keroro 062.avi",
            node_metrics=(
                CounterIncrement(counter=NodeCounter.SOURCE_ALERTS, labels=_ED2K_REAPPEARED),
            ),
            notification=SourceAlert(
                kind=SourceAlertKind.REAPPEARED,
                source=_SOURCE,
                source_name="AnimuseeFMR",
                absent_for=timedelta(hours=26),
                target_titles=_062A,
                filename="Keroro 062.avi",
                node_id=_NODE_ID,
            ),
        ),
    ),
]


# Also the catalog's guardrail: a policy writing an instruction that misfits its node metric raises.
def test_plan_observability_maps_every_event() -> None:
    for event, expected in CASES:
        assert plan_observability(event) == expected, f"wrong ObservabilityPlan for {event!r}"


_HASH = "8f3a1c0b9e7d44a2b6c1f0e9d8a7b6c5"


def _decisions(*changes: ev.DecisionChange) -> ev.DecisionsRecorded:
    return ev.DecisionsRecorded(
        file=FileKey(network=Network.ED2K, native_id=_HASH),
        filename="Keroro 062.avi",
        size_bytes=367_185_920,
        changes=changes,
        node_id=_NODE_ID,
    )


def _decision(target_id: TargetId, *, label: str) -> FileTargetDecision:
    """The decision a log line names ``label``: a tier, or ``retracted``."""
    if label == "retracted":
        return Retraction(target_id=target_id)
    return DecisionRecord(target_id=target_id, rule_name="rule", tier=DecisionTier(label))


def _change(target_id: TargetId, *, before: str | None, after: str) -> ev.DecisionChange:
    title = {"062A": "Les demoiselles cambrioleuses", "062B": "Le grand combat sous-marin"}
    previous = None if before is None else _decision(target_id, label=before)
    return ev.DecisionChange(
        target_id=target_id,
        title=title[target_id],
        previous_decision=previous,
        new_decision=_decision(target_id, label=after),
    )


@pytest.mark.parametrize(
    ("before", "after", "notified"),
    [
        (None, "notify", True),
        (None, "download", True),
        ("retracted", "notify", True),
        ("retracted", "download", True),
        ("notify", "download", True),
        ("catalog", "notify", True),
        ("download", "download", False),
        ("notify", "notify", False),
        ("download", "notify", False),
        ("notify", "catalog", False),
        (None, "catalog", False),
        ("download", "retracted", False),
    ],
)
def test_only_a_rise_to_notify_or_download_reaches_the_community(
    *, before: str | None, after: str, notified: bool
) -> None:
    plan = plan_observability(_decisions(_change(TargetId("062A"), before=before, after=after)))
    assert (plan.notification is not None) == notified
    assert plan.node_metrics == (
        CounterIncrement(
            counter=NodeCounter.DECISIONS,
            labels=DecisionLabels(
                tier="retracted" if after == "retracted" else DecisionTier(after)
            ),
        ),
    )


_062A_062B = (
    ev.TargetTitle(target_id=TargetId("062A"), title="Les demoiselles cambrioleuses"),
    ev.TargetTitle(target_id=TargetId("062B"), title="Le grand combat sous-marin"),
)


def test_a_file_with_risen_targets_is_one_rise_naming_the_file_and_targets() -> None:
    plan = plan_observability(
        _decisions(
            _change(TargetId("062A"), before=None, after="download"),
            _change(TargetId("062B"), before=None, after="notify"),
        )
    )
    assert plan.notification == TierRise(
        tier=DecisionTier.DOWNLOAD,
        target_titles=_062A_062B,
        filename="Keroro 062.avi",
        size_bytes=367_185_920,
        ed2k_link=f"ed2k://|file|Keroro%20062.avi|367185920|{_HASH}|/",
        node_id=_NODE_ID,
    )
    assert plan.node_metrics == (
        CounterIncrement(
            counter=NodeCounter.DECISIONS, labels=DecisionLabels(tier=DecisionTier.DOWNLOAD)
        ),
        CounterIncrement(
            counter=NodeCounter.DECISIONS, labels=DecisionLabels(tier=DecisionTier.NOTIFY)
        ),
    )


def test_the_rise_lists_only_the_risen_targets_under_their_highest_tier() -> None:
    plan = plan_observability(
        _decisions(
            _change(TargetId("062A"), before="catalog", after="notify"),
            _change(TargetId("062B"), before="notify", after="retracted"),
        )
    )
    assert isinstance(plan.notification, TierRise)
    assert (plan.notification.tier, plan.notification.target_titles) == (
        DecisionTier.NOTIFY,
        (ev.TargetTitle(target_id=TargetId("062A"), title="Les demoiselles cambrioleuses"),),
    )


def test_decisions_log_one_line_listing_every_change() -> None:
    plan = plan_observability(
        _decisions(
            _change(TargetId("062A"), before=None, after="download"),
            _change(TargetId("062B"), before="notify", after="retracted"),
        )
    )
    assert plan.severity == Severity.INFO
    assert plan.message == (
        f"decisions for Keroro 062.avi ({_HASH}): 062A none → download, 062B notify → retracted"
    )


def test_a_change_without_a_rise_has_no_notification() -> None:
    plan = plan_observability(
        _decisions(_change(TargetId("062A"), before="download", after="notify"))
    )
    assert plan.notification is None


def test_a_completed_download_notifies_its_targets_and_file() -> None:
    plan = plan_observability(
        ev.DownloadCompleted(
            file=FileKey(network=Network.ED2K, native_id=_HASH),
            filename="Keroro `062`.avi",
            target_titles=_062A_062B,
            node_id=_NODE_ID,
        )
    )
    assert plan == ObservabilityPlan(
        severity=Severity.SUCCESS,
        message="✅ download completed: 062A, 062B",
        node_metrics=(CounterIncrement(counter=NodeCounter.DOWNLOADS_COMPLETED),),
        notification=CompletedDownload(
            target_titles=_062A_062B, filename="Keroro `062`.avi", node_id=_NODE_ID
        ),
    )


def test_a_completed_download_without_a_target_logs_unknown() -> None:
    plan = plan_observability(
        ev.DownloadCompleted(
            file=FileKey(network=Network.ED2K, native_id=_HASH),
            filename="Keroro 062.avi",
            target_titles=(),
            node_id=_NODE_ID,
        )
    )
    assert plan.message == "✅ download completed: unknown"


@pytest.mark.parametrize(
    ("notification", "audience"),
    [
        (
            TierRise(
                tier=DecisionTier.NOTIFY,
                target_titles=_062A,
                filename="Keroro 062.avi",
                size_bytes=1,
                ed2k_link="ed2k://",
                node_id=_NODE_ID,
            ),
            "community",
        ),
        (
            SourceAlert(
                kind=SourceAlertKind.FIRST_USEFUL,
                source=_SOURCE,
                source_name=None,
                absent_for=None,
                target_titles=(),
                filename="k.avi",
                node_id=_NODE_ID,
            ),
            "community",
        ),
        (
            CompletedDownload(target_titles=_062A, filename="Keroro 062.avi", node_id=_NODE_ID),
            "community",
        ),
        (RelayedLogLine(message="x", severity=Severity.WARNING, node_id=_NODE_ID), "operations"),
    ],
)
def test_a_notification_goes_to_the_audience_its_kind_names(
    *, notification: Notification, audience: str
) -> None:
    assert audience_of(notification) is Audience(audience)


def test_a_source_without_a_name_or_a_target_is_alerted_without_them() -> None:
    plan = plan_observability(
        ev.SourceFirstUseful(
            source=_SOURCE,
            source_name=None,
            file=_FILE,
            filename="Keroro 062.avi",
            target_titles=(),
            node_id=_NODE_ID,
        )
    )
    assert plan.notification == SourceAlert(
        kind=SourceAlertKind.FIRST_USEFUL,
        source=_SOURCE,
        source_name=None,
        absent_for=None,
        target_titles=(),
        filename="Keroro 062.avi",
        node_id=_NODE_ID,
    )
