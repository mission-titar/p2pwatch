from p2pwatch.application.ports.driven.download_client import DownloadClient
from p2pwatch.domain.download.request import DownloadRequest
from p2pwatch.domain.download.status import DownloadStatus


class FakeDownloadClient(DownloadClient):
    """SCRIPTED ``downloads()`` snapshots, captures the started requests."""

    def __init__(
        self,
        *,
        listed: list[tuple[DownloadStatus, ...]] | None = None,
        list_failures: list[Exception] | None = None,
        start_failures: list[Exception] | None = None,
    ) -> None:
        self._listed = list(listed or [()])
        self._list_failures = list(list_failures or [])
        self._start_failures = list(start_failures or [])
        self.started: list[DownloadRequest] = []

    async def start(self, request: DownloadRequest) -> None:
        if self._start_failures:
            raise self._start_failures.pop(0)
        self.started.append(request)

    async def downloads(self) -> tuple[DownloadStatus, ...]:
        if self._list_failures:
            raise self._list_failures.pop(0)
        return self._listed.pop(0) if self._listed else ()
