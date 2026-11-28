"""Each watched function's latest progress: how long each has made none, from the first look."""

from datetime import timedelta

from p2pwatch.application.steps.function_progress import FunctionProgress
from p2pwatch.domain.identifiers import Channel, ClientName
from p2pwatch.domain.watched_function import WatchedCrawl
from tests.fakes.adapters.driven.fake_time import FakeTime

_ED2K = WatchedCrawl(client_name=ClientName("amuled"), channel=Channel("ed2k"))
_KAD = WatchedCrawl(client_name=ClientName("amuled"), channel=Channel("kad"))


def test_every_function_counts_from_the_first_look_at_any_the_time_before_for_none() -> None:
    fake_time = FakeTime()
    progress = FunctionProgress(monotonic_clock=fake_time.monotonic)
    fake_time.advance(timedelta(minutes=30))  # the start's reevaluation, say

    assert progress.time_without_progress(_ED2K) == timedelta(0)
    fake_time.advance(timedelta(minutes=4))
    assert progress.time_without_progress(_KAD) == timedelta(minutes=4)


def test_a_function_counts_from_its_latest_progress_alone() -> None:
    fake_time = FakeTime()
    progress = FunctionProgress(monotonic_clock=fake_time.monotonic)
    progress.time_without_progress(_KAD)
    fake_time.advance(timedelta(minutes=3))
    progress.record_progress(_KAD)
    fake_time.advance(timedelta(minutes=2))

    assert progress.time_without_progress(_KAD) == timedelta(minutes=2)
    assert progress.time_without_progress(_ED2K) == timedelta(minutes=5)
