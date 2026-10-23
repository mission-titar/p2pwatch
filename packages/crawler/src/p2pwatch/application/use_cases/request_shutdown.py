"""Requests the crawler's shutdown through its run state."""

from p2pwatch.application.ports.driven.run_state_writer import RunStateWriter
from p2pwatch.application.ports.driving.shutdown_requester import ShutdownRequester


class RequestShutdown(ShutdownRequester):
    """The run state changes on the crawler's loop, after the call has returned."""

    def __init__(self, run_state: RunStateWriter) -> None:
        self._run_state = run_state

    def request_shutdown(self) -> None:
        self._run_state.set_shutdown_requested()
