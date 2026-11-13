from p2pwatch.application.ports.driven.status_client import StatusClient
from p2pwatch.domain.client_errors import ClientError
from p2pwatch.domain.status_reading import ClientStatus


class FakeStatusClient(StatusClient):
    """One scripted reading per call."""

    def __init__(self, readings: list[ClientStatus | ClientError]) -> None:
        self._readings = readings

    async def status(self) -> ClientStatus:
        reading = self._readings.pop(0)
        if isinstance(reading, ClientError):
            raise reading
        return reading
