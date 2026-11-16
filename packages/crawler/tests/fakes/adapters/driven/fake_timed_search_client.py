import asyncio

from p2pwatch.application.ports.driven.search_client import SearchClient
from p2pwatch.domain.identifiers import Channel, Keyword
from p2pwatch.domain.observation import ReportedFile
from p2pwatch.domain.search.answer import SearchAnswer


class FakeTimedSearchClient(SearchClient):
    """A search takes its channel's duration in loop time; scripted failures come first; a search
    of a broken keyword or channel meets a bug once its duration has passed."""

    def __init__(
        self,
        durations: dict[Channel, float],
        *,
        search_failures: list[Exception] | None = None,
        reported_files: tuple[ReportedFile, ...] = (),
        broken_keywords: frozenset[Keyword] = frozenset(),
        broken_channels: frozenset[Channel] = frozenset(),
    ) -> None:
        self._channels = tuple(durations)
        self._durations = durations
        self._search_failures = search_failures or []
        self._reported_files = reported_files
        self._broken_keywords = broken_keywords
        self._broken_channels = broken_channels
        self.searches: list[tuple[float, Keyword, Channel]] = []

    def channels(self) -> tuple[Channel, ...]:
        return self._channels

    async def search(
        self, keyword: Keyword, *, channel: Channel, budget_seconds: float
    ) -> SearchAnswer:
        self.searches.append((asyncio.get_running_loop().time(), keyword, channel))
        if self._search_failures:
            raise self._search_failures.pop(0)
        await asyncio.sleep(self._durations[channel])  # noqa: TID251
        if keyword in self._broken_keywords or channel in self._broken_channels:
            raise RuntimeError("an answer the mapper cannot read")
        return SearchAnswer(reported_files=self._reported_files, skipped_result_count=0)
