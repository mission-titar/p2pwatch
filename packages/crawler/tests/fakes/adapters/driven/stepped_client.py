import asyncio
from datetime import timedelta

from p2pwatch.domain.client_errors import ClientError
from p2pwatch.domain.status_reading import ClientStatus
from tests.fakes.adapters.driven.fake_time import FakeTime
from tests.fakes.adapters.driven.scripted_client import ScriptedClient


class SteppedClient(ScriptedClient):
    """Steps the wall clock forward an hour between its first reading and its second."""

    def __init__(
        self,
        readings: list[ClientStatus | ClientError],
        shutdown: asyncio.Event,
        fake_time: FakeTime,
    ) -> None:
        super().__init__(readings, shutdown)
        self._fake_time = fake_time
        self._calls = 0

    async def status(self) -> ClientStatus:
        self._calls += 1
        if self._calls == 2:
            self._fake_time.step_wall(timedelta(hours=1))
        return await super().status()
