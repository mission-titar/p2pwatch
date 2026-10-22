"""``RequestShutdown``: requests the run state's shutdown, and changes nothing else."""

from p2pwatch.application.use_cases.request_shutdown import RequestShutdown
from tests.fakes.adapters.driven.fake_run_state import FakeRunState


def test_a_shutdown_request_reaches_the_run_state() -> None:
    run_state = FakeRunState()

    RequestShutdown(run_state).request_shutdown()

    assert run_state.changes == ["shut_down"]
