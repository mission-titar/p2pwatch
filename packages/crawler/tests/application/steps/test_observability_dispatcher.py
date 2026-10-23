"""The dispatch step: log + metrics always; notification by audience, failure/timeout absorbed."""

from typing import Literal

import pytest

from catalog_matching.domain.decision_tier import DecisionTier
from catalog_matching.domain.engine import DecisionRecord
from p2pwatch.application.ports.driven.metrics_recorder import MetricsRecorder
from p2pwatch.application.ports.driven.notifier import Notifier
from p2pwatch.application.steps.observability_dispatcher import (
    ObservabilityDispatcher,
    log_at_severity,
)
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.observability import events as ev
from p2pwatch.domain.observability.policy import Audience, Severity
from tests.fakes.adapters.driven.fake_hanging_notifier import FakeHangingNotifier
from tests.fakes.adapters.driven.fake_logger import FakeLogger, LoggedLine
from tests.fakes.adapters.driven.fake_metrics_recorder import FakeMetricsRecorder
from tests.fakes.adapters.driven.fake_notifier import FakeNotifier
from tests.fakes.adapters.driven.fake_raising_notifier import FakeRaisingNotifier

_NODE = "titar-node-1"
_COMPLETED = ev.DownloadCompleted(
    FileKey(Network.ED2K, "a" * 32), "Keroro 062.avi", (ev.TargetTitle("062A", "t"),)
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
        ev.ObservationRecorded(client_name="amuled", channel="ed2k"), _NODE
    )
    assert [m.name.value for m in metrics_recorder.applied] == ["p2pwatch_observations"]
    assert notifier.calls == []  # ObservationRecorded has no audience


@pytest.mark.asyncio
async def test_two_metrics_one_event() -> None:
    metrics_recorder, notifier = FakeMetricsRecorder(), FakeNotifier()
    await _dispatcher(metrics_recorder, notifier).dispatch(
        ev.ChannelStatusSampled(
            client_name="amuled", channel="kad", connected=True, connectable=True
        ),
        _NODE,
    )
    assert [m.name.value for m in metrics_recorder.applied] == [
        "p2pwatch_channel_connected",
        "p2pwatch_channel_connectable",
    ]


@pytest.mark.asyncio
async def test_notifies_the_message_when_there_is_no_separate_body() -> None:
    metrics_recorder, notifier = FakeMetricsRecorder(), FakeNotifier()
    await _dispatcher(metrics_recorder, notifier).dispatch(
        ev.CrawlerStarted(download_enabled=True), _NODE
    )
    assert notifier.calls == [
        (Audience.OPERATIONS, "", "🟢 node online (download on)", Severity.INFO)
    ]
    assert notifier.node_ids == [_NODE]


@pytest.mark.asyncio
async def test_logs_the_message_but_notifies_the_body() -> None:
    logger, notifier = FakeLogger(), FakeNotifier()
    download = DecisionRecord("062A", "rule", DecisionTier.DOWNLOAD)
    change = ev.DecisionChange("062A", "Les demoiselles cambrioleuses", None, download)
    await _dispatcher(FakeMetricsRecorder(), notifier, logger).dispatch(
        ev.DecisionsRecorded(FileKey(Network.ED2K, "a" * 32), "Keroro 062.avi", 1024, (change,)),
        _NODE,
    )
    assert logger.lines[-1].message.startswith("decisions for Keroro 062.avi")
    assert [(a, t, b.splitlines()[0]) for a, t, b, _ in notifier.calls] == [
        (Audience.COMMUNITY, "📥 Download", "**Targets**")
    ]


@pytest.mark.asyncio
async def test_log_level_matches_severity() -> None:
    logger = FakeLogger()
    await _dispatcher(FakeMetricsRecorder(), FakeNotifier(), logger).dispatch(
        ev.ClientUnreachable("amuled"), _NODE
    )
    assert [line.level for line in logger.lines] == ["warning"]


@pytest.mark.parametrize(
    ("severity", "level"),
    [
        (Severity.DEBUG, "debug"),
        (Severity.INFO, "info"),
        (Severity.SUCCESS, "info"),
        (Severity.WARNING, "warning"),
        (Severity.ERROR, "error"),
    ],
)
def test_each_severity_logs_at_its_level(
    severity: Severity, level: Literal["debug", "info", "warning", "error"]
) -> None:
    logger = FakeLogger()
    log_at_severity(logger, severity, "100% done")
    assert logger.lines == [LoggedLine(level, "100% done")]


@pytest.mark.asyncio
async def test_notification_failure_is_absorbed() -> None:
    logger, metrics_recorder = FakeLogger(), FakeMetricsRecorder()
    await _dispatcher(metrics_recorder, FakeRaisingNotifier(), logger).dispatch(_COMPLETED, _NODE)
    assert metrics_recorder.applied  # the metric went through despite the notification failure
    assert logger.lines[-1] == LoggedLine("warning", "notification community failed (canal mort)")


@pytest.mark.asyncio
async def test_notification_timeout_is_absorbed() -> None:
    metrics_recorder = FakeMetricsRecorder()
    # short timeout + hanging notifier → wait_for raises TimeoutError, absorbed.
    await _dispatcher(metrics_recorder, FakeHangingNotifier(), timeout=0.01).dispatch(
        _COMPLETED, _NODE
    )
    assert metrics_recorder.applied


@pytest.mark.asyncio
async def test_emit_dispatches_the_event() -> None:
    metrics_recorder = FakeMetricsRecorder()
    await _dispatcher(metrics_recorder, FakeNotifier()).emit(_COMPLETED, _NODE)
    assert metrics_recorder.applied
