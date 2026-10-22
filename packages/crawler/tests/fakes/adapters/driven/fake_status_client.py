import asyncio

from p2pwatch.application.ports.driven.status_client import StatusClient
from p2pwatch.domain.client_errors import ClientError
from p2pwatch.domain.status_reading import ClientStatus


class FakeStatusClient(StatusClient):
    """One scripted reading per call; the last one asks for shutdown."""

    def __init__(self, readings: list[ClientStatus | ClientError], shutdown: asyncio.Event) -> None:
        self._readings = readings
        self._shutdown = shutdown

    async def status(self) -> ClientStatus:
        reading = self._readings.pop(0)
        if not self._readings:
            self._shutdown.set()
        if isinstance(reading, ClientError):
            raise reading
        return reading
