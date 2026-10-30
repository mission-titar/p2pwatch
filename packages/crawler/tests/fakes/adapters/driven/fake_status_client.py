from p2pwatch.application.ports.driven.run_state_writer import RunStateWriter
from p2pwatch.application.ports.driven.status_client import StatusClient
from p2pwatch.domain.client_errors import ClientError
from p2pwatch.domain.status_reading import ClientStatus


class FakeStatusClient(StatusClient):
    """One scripted reading per call; the last one asks for shutdown."""

    def __init__(
        self, readings: list[ClientStatus | ClientError], *, run_state: RunStateWriter
    ) -> None:
        self._readings = readings
        self._run_state = run_state

    async def status(self) -> ClientStatus:
        reading = self._readings.pop(0)
        if not self._readings:
            self._run_state.set_shutdown_requested()
        if isinstance(reading, ClientError):
            raise reading
        return reading
