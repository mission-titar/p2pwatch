"""The dispatcher: log + metrics always; notification by audience, failure/timeout absorbed."""

import logging

import pytest

from p2pwatch.adapters.driven.observability.dispatcher import ObservabilityDispatcher
from p2pwatch.application.ports.driven.metrics_recorder import MetricsRecorder
from p2pwatch.application.ports.driven.notifier import Notifier
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.observability import events as ev
from p2pwatch.domain.observability.policy import Audience, Severity
from tests.fakes.adapters.driven.fake_metrics_recorder import FakeMetricsRecorder
from tests.fakes.adapters.driven.hanging_notifier import HangingNotifier
from tests.fakes.adapters.driven.raising_notifier import RaisingNotifier
from tests.fakes.adapters.driven.recording_notifier import RecordingNotifier

_NODE = "titar-node-1"
_COMPLETED = ev.DownloadCompleted(
    FileKey(Network.ED2K, "a" * 32), "Keroro 062.avi", (ev.TargetTitle("062A", "t"),)
)


def _dispatcher(
    metrics_recorder: MetricsRecorder, notifier: Notifier, timeout: float = 5.0
) -> ObservabilityDispatcher:
    return ObservabilityDispatcher(
        metrics_recorder=metrics_recorder, notifier=notifier, notification_timeout_seconds=timeout
    )


@pytest.mark.asyncio
async def test_logs_and_applies_metrics_no_audience() -> None:
    metrics_recorder, notifier = FakeMetricsRecorder(), RecordingNotifier()
    await _dispatcher(metrics_recorder, notifier).emit(
        ev.ObservationRecorded(client_name="amuled", channel="ed2k"), _NODE
    )
    assert [m.name.value for m in metrics_recorder.applied] == ["p2pwatch_observations"]
    assert notifier.calls == []  # ObservationRecorded has no audience


@pytest.mark.asyncio
async def test_two_metrics_one_event() -> None:
    metrics_recorder, notifier = FakeMetricsRecorder(), RecordingNotifier()
    await _dispatcher(metrics_recorder, notifier).emit(
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
    metrics_recorder, notifier = FakeMetricsRecorder(), RecordingNotifier()
    await _dispatcher(metrics_recorder, notifier).emit(
        ev.CrawlerStarted(download_enabled=True), _NODE
    )
    assert notifier.calls == [
        (Audience.OPERATIONS, "", "🟢 node online (download on)", Severity.INFO)
    ]
    assert notifier.node_ids == [_NODE]


@pytest.mark.asyncio
async def test_logs_the_message_but_notifies_the_body(caplog: pytest.LogCaptureFixture) -> None:
    metrics_recorder, notifier = FakeMetricsRecorder(), RecordingNotifier()
    change = ev.DecisionChange("062A", "Les demoiselles cambrioleuses", None, "download")
    with caplog.at_level(logging.INFO, logger="p2pwatch.observability"):
        await _dispatcher(metrics_recorder, notifier).emit(
            ev.DecisionsRecorded(
                FileKey(Network.ED2K, "a" * 32), "Keroro 062.avi", 1024, (change,)
            ),
            _NODE,
        )
    assert caplog.records[-1].getMessage().startswith("decisions for Keroro 062.avi")
    assert [(a, t, b.splitlines()[0]) for a, t, b, _ in notifier.calls] == [
        (Audience.COMMUNITY, "📥 Download", "**Targets**")
    ]


@pytest.mark.asyncio
async def test_log_level_matches_severity(caplog: pytest.LogCaptureFixture) -> None:
    metrics_recorder, notifier = FakeMetricsRecorder(), RecordingNotifier()
    with caplog.at_level(logging.DEBUG, logger="p2pwatch.observability"):
        await _dispatcher(metrics_recorder, notifier).emit(ev.ClientUnreachable("amuled"), _NODE)
    assert caplog.records[-1].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_a_success_logs_as_info(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG, logger="p2pwatch.observability"):
        await _dispatcher(FakeMetricsRecorder(), RecordingNotifier()).emit(_COMPLETED, _NODE)
    assert caplog.records[-1].levelno == logging.INFO


@pytest.mark.asyncio
async def test_notification_failure_is_absorbed(caplog: pytest.LogCaptureFixture) -> None:
    metrics_recorder = FakeMetricsRecorder()
    with caplog.at_level(logging.WARNING, logger="p2pwatch.observability"):
        await _dispatcher(metrics_recorder, RaisingNotifier()).emit(_COMPLETED, _NODE)
    assert metrics_recorder.applied  # the metric went through despite the notification failure
    assert any("failed" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_notification_timeout_is_absorbed() -> None:
    metrics_recorder = FakeMetricsRecorder()
    # short timeout + hanging notifier → wait_for raises TimeoutError, absorbed.
    await _dispatcher(metrics_recorder, HangingNotifier(), timeout=0.01).emit(_COMPLETED, _NODE)
    assert metrics_recorder.applied
