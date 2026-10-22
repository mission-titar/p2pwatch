"""``ResumeCrawl``: resumes the run state, and changes nothing else."""

from p2pwatch.application.use_cases.resume_crawl import ResumeCrawl
from tests.fakes.adapters.driven.fake_run_state_store import FakeRunStateStore


def test_resuming_the_crawl_resumes_the_run_state() -> None:
    run_state = FakeRunStateStore()

    ResumeCrawl(run_state).resume_crawl()

    assert run_state.changes == ["resume"]
