"""``PauseCrawl``: pauses the run state, and changes nothing else."""

from p2pwatch.application.use_cases.pause_crawl import PauseCrawl
from tests.fakes.adapters.driven.fake_run_state_store import FakeRunStateStore


def test_pausing_the_crawl_pauses_the_run_state() -> None:
    run_state = FakeRunStateStore()

    PauseCrawl(run_state).pause_crawl()

    assert run_state.is_paused()
    assert not run_state.is_shutdown_requested()
