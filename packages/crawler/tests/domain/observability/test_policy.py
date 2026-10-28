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

_AMULED_KAD = ChannelLabels(ClientName("amuled"), Channel("kad"))
_AMULED_ED2K = ChannelLabels(ClientName("amuled"), Channel("ed2k"))
_ED2K_FIRST_USEFUL = SourceAlertLabels(Network.ED2K, SourceAlertKind.FIRST_USEFUL)
_ED2K_REAPPEARED = SourceAlertLabels(Network.ED2K, SourceAlertKind.REAPPEARED)
_SOURCE = SourceKey(Network.ED2K, "1f2e3d4c" * 4)
_FILE = FileKey(Network.ED2K, "8f3a1c0b9e7d44a2b6c1f0e9d8a7b6c5")
_062A = (ev.TargetTitle(TargetId("062A"), "Les demoiselles cambrioleuses"),)
_NODE = NodeId("titar-node-1")


def _relayed(
    severity: Severity, message: str, node_metrics: tuple[CounterIncrement | GaugeSetting, ...] = ()
) -> ObservabilityPlan:
    """An operations plan: its log line relayed under the event's node."""
    return ObservabilityPlan(
        severity, message, node_metrics, RelayedLogLine(message, severity, _NODE)
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
            Severity.DEBUG,
            "search ed2k: 7 observation(s)",
            (
                CounterIncrement(NodeCounter.SEARCHES, _AMULED_ED2K),
                CounterIncrement(NodeCounter.SEARCH_RESULTS_SKIPPED, _AMULED_ED2K, 2.0),
            ),
        ),
    ),
    (
        ev.ClientUnreachable(client_name=ClientName("slskd")),
        ObservabilityPlan(
            Severity.WARNING,
            "slskd unreachable",
            (CounterIncrement(NodeCounter.CLIENT_UNREACHABLE, ClientLabels(ClientName("slskd"))),),
        ),
    ),
    (
        ev.SearchFailed(client_name=ClientName("amuled"), channel=Channel("kad")),
        ObservabilityPlan(
            Severity.WARNING,
            "search failed on kad",
            (CounterIncrement(NodeCounter.SEARCH_FAILURES, _AMULED_KAD),),
        ),
    ),
    (
        ev.ObservationRecorded(client_name=ClientName("amuled"), channel=Channel("kad")),
        ObservabilityPlan(
            Severity.DEBUG,
            "observation recorded (kad)",
            (CounterIncrement(NodeCounter.OBSERVATIONS, _AMULED_KAD),),
        ),
    ),
    (
        ev.DownloadQueued(target_id=TargetId("062A")),
        ObservabilityPlan(
            Severity.INFO,
            "download queued: 062A",
            (CounterIncrement(NodeCounter.DOWNLOADS_QUEUED),),
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
            Severity.DEBUG,
            "status amuled kad: connected yes, connectable no",
            (
                GaugeSetting(NodeGauge.CHANNEL_CONNECTED, _AMULED_KAD, 1.0),
                GaugeSetting(NodeGauge.CHANNEL_CONNECTABLE, _AMULED_KAD, 0.0),
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
            Severity.DEBUG,
            "status amuled kad: connected unknown, connectable unknown",
            (
                GaugeSetting(NodeGauge.CHANNEL_CONNECTED, _AMULED_KAD, None),
                GaugeSetting(NodeGauge.CHANNEL_CONNECTABLE, _AMULED_KAD, None),
            ),
        ),
    ),
    (
        ev.ChannelDegraded(
            client_name=ClientName("amuled"),
            channel=Channel("ed2k"),
            field="connected",
            degraded_for_seconds=300.0,
            node_id=_NODE,
        ),
        _relayed(Severity.WARNING, "amuled ed2k: off its network for 5 min"),
    ),
    (
        ev.ChannelDegraded(
            client_name=ClientName("amuled"),
            channel=Channel("kad"),
            field="connectable",
            degraded_for_seconds=300.0,
            node_id=_NODE,
        ),
        _relayed(Severity.WARNING, "amuled kad: not connectable for 5 min"),
    ),
    (
        ev.ChannelRecovered(
            client_name=ClientName("amuled"),
            channel=Channel("ed2k"),
            field="connected",
            node_id=_NODE,
        ),
        _relayed(Severity.INFO, "amuled ed2k: back on its network"),
    ),
    (
        ev.ChannelRecovered(
            client_name=ClientName("amuled"),
            channel=Channel("kad"),
            field="connectable",
            node_id=_NODE,
        ),
        _relayed(Severity.INFO, "amuled kad: connectable again"),
    ),
    (
        ev.ClientUnreachableLasting(
            client_name=ClientName("amuled"), unreachable_for_seconds=120.0, node_id=_NODE
        ),
        _relayed(Severity.WARNING, "amuled unreachable for 2 min"),
    ),
    (
        ev.ClientReachableAgain(client_name=ClientName("amuled"), node_id=_NODE),
        _relayed(Severity.INFO, "amuled reachable again"),
    ),
    (
        ev.FreeSpaceSampled(free_bytes=5_000),
        ObservabilityPlan(
            Severity.DEBUG,
            "download disk free: 5000 bytes",
            (GaugeSetting(NodeGauge.DISK_FREE_BYTES, None, 5_000.0),),
        ),
    ),
    (
        ev.DiskSpaceLow(free_bytes=3 * 2**29, min_free_bytes=10 * 2**30, node_id=_NODE),
        _relayed(
            Severity.WARNING,
            "download disk low: 1.5 GiB free, under the 10.0 GiB floor (no new download)",
        ),
    ),
    (
        ev.CrawlerStarted(download_enabled=True, node_id=_NODE),
        _relayed(
            Severity.INFO,
            "🟢 node online (download on)",
            (GaugeSetting(NodeGauge.CRAWLER_UP, None, 1.0),),
        ),
    ),
    (
        ev.CrawlerStarted(download_enabled=False, node_id=_NODE),
        _relayed(
            Severity.INFO,
            "🟢 node online (download off)",
            (GaugeSetting(NodeGauge.CRAWLER_UP, None, 1.0),),
        ),
    ),
    (
        ev.SourceFirstUseful(_SOURCE, "AnimuseeFMR", _FILE, "Keroro 062.avi", _062A, _NODE),
        ObservabilityPlan(
            Severity.INFO,
            "source 1f2e3d4c… useful for the first time: Keroro 062.avi",
            (CounterIncrement(NodeCounter.SOURCE_ALERTS, _ED2K_FIRST_USEFUL),),
            SourceAlert(
                SourceAlertKind.FIRST_USEFUL,
                _SOURCE,
                "AnimuseeFMR",
                None,
                _062A,
                "Keroro 062.avi",
                _NODE,
            ),
        ),
    ),
    (
        ev.SourceReappeared(
            _SOURCE, "AnimuseeFMR", _FILE, "Keroro 062.avi", _062A, 93_600.0, _NODE
        ),
        ObservabilityPlan(
            Severity.INFO,
            "source 1f2e3d4c… reappeared after 26 h: Keroro 062.avi",
            (CounterIncrement(NodeCounter.SOURCE_ALERTS, _ED2K_REAPPEARED),),
            SourceAlert(
                SourceAlertKind.REAPPEARED,
                _SOURCE,
                "AnimuseeFMR",
                timedelta(hours=26),
                _062A,
                "Keroro 062.avi",
                _NODE,
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
        file=FileKey(Network.ED2K, _HASH),
        filename="Keroro 062.avi",
        size_bytes=367_185_920,
        changes=changes,
        node_id=_NODE,
    )


def _decision(target_id: TargetId, label: str) -> FileTargetDecision:
    """The decision a log line names ``label``: a tier, or ``retracted``."""
    if label == "retracted":
        return Retraction(target_id)
    return DecisionRecord(target_id, "rule", DecisionTier(label))


def _change(target_id: TargetId, before: str | None, after: str) -> ev.DecisionChange:
    title = {"062A": "Les demoiselles cambrioleuses", "062B": "Le grand combat sous-marin"}
    previous = None if before is None else _decision(target_id, before)
    return ev.DecisionChange(target_id, title[target_id], previous, _decision(target_id, after))


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
    before: str | None, after: str, notified: bool
) -> None:
    plan = plan_observability(_decisions(_change(TargetId("062A"), before, after)))
    assert (plan.notification is not None) == notified
    assert plan.node_metrics == (
        CounterIncrement(
            NodeCounter.DECISIONS,
            DecisionLabels("retracted" if after == "retracted" else DecisionTier(after)),
        ),
    )


_062A_062B = (
    ev.TargetTitle(TargetId("062A"), "Les demoiselles cambrioleuses"),
    ev.TargetTitle(TargetId("062B"), "Le grand combat sous-marin"),
)


def test_a_file_with_risen_targets_is_one_rise_naming_the_file_and_targets() -> None:
    plan = plan_observability(
        _decisions(
            _change(TargetId("062A"), None, "download"), _change(TargetId("062B"), None, "notify")
        )
    )
    assert plan.notification == TierRise(
        DecisionTier.DOWNLOAD,
        _062A_062B,
        "Keroro 062.avi",
        367_185_920,
        f"ed2k://|file|Keroro%20062.avi|367185920|{_HASH}|/",
        _NODE,
    )
    assert plan.node_metrics == (
        CounterIncrement(NodeCounter.DECISIONS, DecisionLabels(DecisionTier.DOWNLOAD)),
        CounterIncrement(NodeCounter.DECISIONS, DecisionLabels(DecisionTier.NOTIFY)),
    )


def test_the_rise_lists_only_the_risen_targets_under_their_highest_tier() -> None:
    plan = plan_observability(
        _decisions(
            _change(TargetId("062A"), "catalog", "notify"),
            _change(TargetId("062B"), "notify", "retracted"),
        )
    )
    assert isinstance(plan.notification, TierRise)
    assert (plan.notification.tier, plan.notification.target_titles) == (
        DecisionTier.NOTIFY,
        (ev.TargetTitle(TargetId("062A"), "Les demoiselles cambrioleuses"),),
    )


def test_decisions_log_one_line_listing_every_change() -> None:
    plan = plan_observability(
        _decisions(
            _change(TargetId("062A"), None, "download"),
            _change(TargetId("062B"), "notify", "retracted"),
        )
    )
    assert plan.severity == Severity.INFO
    assert plan.message == (
        f"decisions for Keroro 062.avi ({_HASH}): 062A none → download, 062B notify → retracted"
    )


def test_a_change_without_a_rise_has_no_notification() -> None:
    plan = plan_observability(_decisions(_change(TargetId("062A"), "download", "notify")))
    assert plan.notification is None


def test_a_completed_download_notifies_its_targets_and_file() -> None:
    plan = plan_observability(
        ev.DownloadCompleted(FileKey(Network.ED2K, _HASH), "Keroro `062`.avi", _062A_062B, _NODE)
    )
    assert plan == ObservabilityPlan(
        Severity.SUCCESS,
        "✅ download completed: 062A, 062B",
        (CounterIncrement(NodeCounter.DOWNLOADS_COMPLETED),),
        CompletedDownload(_062A_062B, "Keroro `062`.avi", _NODE),
    )


def test_a_completed_download_without_a_target_logs_unknown() -> None:
    plan = plan_observability(
        ev.DownloadCompleted(FileKey(Network.ED2K, _HASH), "Keroro 062.avi", (), _NODE)
    )
    assert plan.message == "✅ download completed: unknown"


@pytest.mark.parametrize(
    ("notification", "audience"),
    [
        (TierRise(DecisionTier.NOTIFY, _062A, "Keroro 062.avi", 1, "ed2k://", _NODE), "community"),
        (
            SourceAlert(SourceAlertKind.FIRST_USEFUL, _SOURCE, None, None, (), "k.avi", _NODE),
            "community",
        ),
        (CompletedDownload(_062A, "Keroro 062.avi", _NODE), "community"),
        (RelayedLogLine("x", Severity.WARNING, _NODE), "operations"),
    ],
)
def test_a_notification_goes_to_the_audience_its_kind_names(
    notification: Notification, audience: str
) -> None:
    assert audience_of(notification) is Audience(audience)


def test_a_source_without_a_name_or_a_target_is_alerted_without_them() -> None:
    plan = plan_observability(
        ev.SourceFirstUseful(_SOURCE, None, _FILE, "Keroro 062.avi", (), _NODE)
    )
    assert plan.notification == SourceAlert(
        SourceAlertKind.FIRST_USEFUL, _SOURCE, None, None, (), "Keroro 062.avi", _NODE
    )
