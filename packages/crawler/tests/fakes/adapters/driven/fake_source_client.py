from datetime import timedelta

from p2pwatch.application.ports.driven.source_client import SourceClient
from p2pwatch.domain.file_key import FileKey
from p2pwatch.domain.source import SourceReading
from tests.fakes.adapters.driven.fake_time import FakeTime


class FakeSourceClient(SourceClient):
    """``readings`` per hash, ``source_reads`` the hashes read, each read advancing ``fake_time``
    by a second when one is given."""

    def __init__(
        self,
        *,
        source_failures: list[Exception] | None = None,
        readings: dict[str, tuple[SourceReading, ...]] | None = None,
        fake_time: FakeTime | None = None,
    ) -> None:
        self._source_failures = list(source_failures or [])
        self._readings = readings or {}
        self._fake_time = fake_time
        self.source_reads: list[str] = []

    async def sources(self, file: FileKey) -> tuple[SourceReading, ...]:
        self.source_reads.append(file.native_id)
        if self._fake_time is not None:
            self._fake_time.advance(timedelta(seconds=1))
        if self._source_failures:
            raise self._source_failures.pop(0)
        return self._readings.get(file.native_id, ())
