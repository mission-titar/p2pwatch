"""``ResumeCrawl``: resumes the run state, and changes nothing else."""

from p2pwatch.application.resume_crawl import ResumeCrawl
from p2pwatch_testing.application.fakes import FakeRunState


def test_resuming_the_crawl_resumes_the_run_state() -> None:
    run_state = FakeRunState()

    ResumeCrawl(run_state).resume_crawl()

    assert run_state.changes == ["resume"]
