"""The stall watch: every minute, each watched function without progress for 15 minutes has its
alert opened, ended once it moves again."""

from collections.abc import Mapping
from datetime import timedelta

import pytest

from p2pwatch.application.steps.function_progress import FunctionProgress
from p2pwatch.application.steps.stall_watch import StallWatch
from p2pwatch.domain.identifiers import Channel, ClientName, NodeId
from p2pwatch.domain.observability.notification import Notification, RelayedLogLine
from p2pwatch.domain.observability.severity import Severity
from p2pwatch.domain.watched_function import WatchedCrawl, WatchedDownloads, WatchedFunction
from tests.fakes.adapters.driven.fake_time import FakeTime
from tests.support.application.steps.node_health import build_node_health
from tests.support.application.steps.observability_dispatcher import ObservabilityOverFakes

pytestmark = pytest.mark.asyncio

_AMULED = ClientName("amuled")
_NODE_ID = NodeId("n1")
_ED2K = WatchedCrawl(client_name=_AMULED, channel=Channel("ed2k"))
_KAD = WatchedCrawl(client_name=_AMULED, channel=Channel("kad"))
_KAD_STALLED = RelayedLogLine(
    message="search stalled on amuled kad for 15 min",
    detail="cause: see the other alerts or the log",
    severity=Severity.WARNING,
    node_id=_NODE_ID,
)
_KAD_MOVING_AGAIN = RelayedLogLine(
    message="search on amuled kad moving again", severity=Severity.INFO, node_id=_NODE_ID
)
_DOWNLOADS = WatchedDownloads(client_name=_AMULED)
_DOWNLOADS_STALLED = RelayedLogLine(
    message="downloads stalled on amuled for 15 min",
    detail="cause: see the other alerts or the log",
    severity=Severity.WARNING,
    node_id=_NODE_ID,
)
_DOWNLOADS_MOVING_AGAIN = RelayedLogLine(
    message="downloads on amuled moving again", severity=Severity.INFO, node_id=_NODE_ID
)


class _Watch:
    """A stall watch over amuled's two channels and its downloads, on one fake timeline, and the
    alerts it sends."""

    def __init__(self) -> None:
        self.time = FakeTime()
        self._progress = FunctionProgress(monotonic_clock=self.time.monotonic)
        self._observability = ObservabilityOverFakes()
        self.watch = StallWatch(
            client_name=_AMULED,
            watched=[_ED2K, _KAD, _DOWNLOADS],
            function_progress=self._progress,
            node_health=build_node_health(observability_dispatcher=self._observability.dispatcher),
            monotonic_clock=self.time.monotonic,
            node_id=_NODE_ID,
        )

    async def alerts_over(
        self, *, minutes: int, moving_from: Mapping[WatchedFunction, int]
    ) -> list[tuple[int, Notification]]:
        """Each alert and the minute it is sent at, over the watch's turns for ``minutes``, each
        function of ``moving_from`` progressing before each turn from its minute on."""
        start, alerts = self.time.monotonic.now(), []
        for _ in range(minutes + 1):
            await self.watch.wait_for_next_turn()
            minute = (self.time.monotonic.now() - start) // timedelta(minutes=1)
            for function, from_minute in moving_from.items():
                if minute >= from_minute:
                    self._progress.record_progress(function)
            sent = len(self._observability.notifications)
            await self.watch.run_once()
            alerts += [(minute, alert) for _, alert in self._observability.notifications[sent:]]
        return alerts


async def test_kad_searches_never_completing_alert_at_15_min_once_until_one_completes() -> None:
    alerts = await _Watch().alerts_over(minutes=20, moving_from={_ED2K: 0, _KAD: 17, _DOWNLOADS: 0})

    assert alerts == [(15, _KAD_STALLED), (17, _KAD_MOVING_AGAIN)]


async def test_the_downloads_and_kad_stalling_together_each_alert_and_end_on_their_own() -> None:
    alerts = await _Watch().alerts_over(
        minutes=20, moving_from={_ED2K: 0, _KAD: 17, _DOWNLOADS: 16}
    )

    assert alerts == [
        (15, _KAD_STALLED),
        (15, _DOWNLOADS_STALLED),
        (16, _DOWNLOADS_MOVING_AGAIN),
        (17, _KAD_MOVING_AGAIN),
    ]


async def test_its_first_look_waits_nothing_and_each_next_a_minute() -> None:
    watch = _Watch()

    for _ in range(3):
        await watch.watch.wait_for_next_turn()
        await watch.watch.run_once()

    assert watch.time.sleeps == [timedelta(minutes=1)] * 2


async def test_the_log_names_it_after_its_client() -> None:
    assert str(_Watch().watch) == "stall watch amuled"
