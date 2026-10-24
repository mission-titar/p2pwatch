"""The dispatch step: log + metrics always; notification by audience, failure/timeout absorbed."""

from typing import Literal

import pytest

from catalog_matching.domain.decision_tier import DecisionTier
from catalog_matching.domain.engine import DecisionRecord
from p2pwatch.application.ports.driven.metrics_recorder import MetricsRecorder
from p2pwatch.application.ports.driven.notifier import Notifier
from p2pwatch.application.steps.observability_dispatcher import ObservabilityDispatcher
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.observability import events as ev
from p2pwatch.domain.observability.notification import RelayedLogLine, TierRise
from p2pwatch.domain.observability.policy import Audience
from p2pwatch.domain.observability.severity import Severity
from tests.fakes.adapters.driven.fake_hanging_notifier import FakeHangingNotifier
from tests.fakes.adapters.driven.fake_logger import FakeLogger, LoggedLine
from tests.fakes.adapters.driven.fake_metrics_recorder import FakeMetricsRecorder
from tests.fakes.adapters.driven.fake_notifier import FakeNotifier
from tests.fakes.adapters.driven.fake_raising_notifier import FakeRaisingNotifier

_NODE = "titar-node-1"
_COMPLETED = ev.DownloadCompleted(
    FileKey(Network.ED2K, "a" * 32), "Keroro 062.avi", (ev.TargetTitle("062A", "t"),), _NODE
)


def _dispatcher(
    metrics_recorder: MetricsRecorder,
    notifier: Notifier,
    logger: FakeLogger | None = None,
    timeout: float = 5.0,
) -> ObservabilityDispatcher:
    return ObservabilityDispatcher(
        logger=logger or FakeLogger(),
        metrics_recorder=metrics_recorder,
        notifier=notifier,
        notification_timeout_seconds=timeout,
    )


@pytest.mark.asyncio
async def test_logs_and_applies_metrics_no_audience() -> None:
    metrics_recorder, notifier = FakeMetricsRecorder(), FakeNotifier()
    await _dispatcher(metrics_recorder, notifier).dispatch(
        ev.ObservationRecorded(client_name="amuled", channel="ed2k")
    )
    assert [m.name.value for m in metrics_recorder.applied] == ["p2pwatch_observations"]
    assert notifier.calls == []  # ObservationRecorded has no audience


@pytest.mark.asyncio
async def test_two_metrics_one_event() -> None:
    metrics_recorder, notifier = FakeMetricsRecorder(), FakeNotifier()
    await _dispatcher(metrics_recorder, notifier).dispatch(
        ev.ChannelStatusSampled(
            client_name="amuled", channel="kad", connected=True, connectable=True
        )
    )
    assert [m.name.value for m in metrics_recorder.applied] == [
        "p2pwatch_channel_connected",
        "p2pwatch_channel_connectable",
    ]


@pytest.mark.asyncio
async def test_relays_the_log_line_under_the_events_node() -> None:
    metrics_recorder, notifier = FakeMetricsRecorder(), FakeNotifier()
    await _dispatcher(metrics_recorder, notifier).dispatch(
        ev.CrawlerStarted(download_enabled=True, node_id=_NODE)
    )
    assert notifier.calls == [
        (Audience.OPERATIONS, RelayedLogLine("🟢 node online (download on)", Severity.INFO, _NODE))
    ]


@pytest.mark.asyncio
async def test_logs_the_message_but_notifies_the_plans_notification() -> None:
    logger, notifier = FakeLogger(), FakeNotifier()
    download = DecisionRecord("062A", "rule", DecisionTier.DOWNLOAD)
    change = ev.DecisionChange("062A", "Les demoiselles cambrioleuses", None, download)
    await _dispatcher(FakeMetricsRecorder(), notifier, logger).dispatch(
        ev.DecisionsRecorded(
            FileKey(Network.ED2K, "a" * 32), "Keroro 062.avi", 1024, (change,), _NODE
        )
    )
    assert logger.lines[-1].message.startswith("decisions for Keroro 062.avi")
    assert notifier.calls == [
        (
            Audience.COMMUNITY,
            TierRise(
                DecisionTier.DOWNLOAD,
                (ev.TargetTitle("062A", "Les demoiselles cambrioleuses"),),
                "Keroro 062.avi",
                1024,
                f"ed2k://|file|Keroro%20062.avi|1024|{'a' * 32}|/",
                _NODE,
            ),
        )
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("event", "level"),
    [
        (ev.ObservationRecorded(client_name="amuled", channel="ed2k"), "debug"),
        (ev.CrawlerStarted(download_enabled=True, node_id=_NODE), "info"),
        (_COMPLETED, "info"),  # a success
        (ev.ClientUnreachable("amuled"), "warning"),
    ],
)
async def test_each_severity_logs_at_its_level(
    event: ev.Event, level: Literal["debug", "info", "warning"]
) -> None:
    logger = FakeLogger()
    await _dispatcher(FakeMetricsRecorder(), FakeNotifier(), logger).dispatch(event)
    assert [line.level for line in logger.lines] == [level]


@pytest.mark.asyncio
async def test_notification_failure_is_absorbed() -> None:
    logger, metrics_recorder = FakeLogger(), FakeMetricsRecorder()
    await _dispatcher(metrics_recorder, FakeRaisingNotifier(), logger).dispatch(_COMPLETED)
    assert metrics_recorder.applied  # the metric went through despite the notification failure
    assert logger.lines[-1] == LoggedLine("warning", "notification community failed (canal mort)")


@pytest.mark.asyncio
async def test_notification_timeout_is_absorbed() -> None:
    metrics_recorder = FakeMetricsRecorder()
    # short timeout + hanging notifier → wait_for raises TimeoutError, absorbed.
    await _dispatcher(metrics_recorder, FakeHangingNotifier(), timeout=0.01).dispatch(_COMPLETED)
    assert metrics_recorder.applied
