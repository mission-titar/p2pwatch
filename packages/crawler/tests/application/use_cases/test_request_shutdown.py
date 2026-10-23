"""``RequestShutdown``: requests the run state's shutdown, and changes nothing else."""

from p2pwatch.application.use_cases.request_shutdown import RequestShutdown
from tests.fakes.adapters.driven.fake_run_state_store import FakeRunStateStore


def test_a_shutdown_request_reaches_the_run_state() -> None:
    run_state = FakeRunStateStore()

    RequestShutdown(run_state).request_shutdown()

    assert run_state.shutdown_requested
    assert not run_state.is_paused()
