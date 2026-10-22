import asyncio

from p2pwatch.application.ports.driven.search_client import SearchClient
from p2pwatch.domain.observation import ReportedFile
from p2pwatch.domain.search.answer import SearchAnswer


class FakeTimedSearchClient(SearchClient):
    """A search takes its channel's duration in loop time; scripted failures come first."""

    def __init__(
        self,
        durations: dict[str, float],
        *,
        search_failures: list[Exception] | None = None,
        reported_files: tuple[ReportedFile, ...] = (),
    ) -> None:
        self._channels = tuple(durations)
        self._durations = durations
        self._search_failures = search_failures or []
        self._reported_files = reported_files
        self.searches: list[tuple[float, str, str]] = []

    def channels(self) -> tuple[str, ...]:
        return self._channels

    async def search(self, keyword: str, channel: str, budget_seconds: float) -> SearchAnswer:
        self.searches.append((asyncio.get_running_loop().time(), keyword, channel))
        if self._search_failures:
            raise self._search_failures.pop(0)
        await asyncio.sleep(self._durations[channel])
        return SearchAnswer(self._reported_files, 0)
