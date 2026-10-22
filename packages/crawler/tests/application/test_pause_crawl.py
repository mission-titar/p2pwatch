"""``PauseCrawl``: pauses the run state, and changes nothing else."""

from p2pwatch.application.pause_crawl import PauseCrawl
from tests.fakes.application.fakes import FakeRunState


def test_pausing_the_crawl_pauses_the_run_state() -> None:
    run_state = FakeRunState()

    PauseCrawl(run_state).pause_crawl()

    assert run_state.changes == ["pause"]
