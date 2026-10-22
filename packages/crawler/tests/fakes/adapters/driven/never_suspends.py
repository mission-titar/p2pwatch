from p2pwatch.application.ports.driven.search_client import SearchClient
from p2pwatch.domain.search.answer import SearchAnswer


class NeverSuspends(SearchClient):
    """A search that returns without suspending, and fails if the loop ran nothing else since
    the previous one."""

    def __init__(self) -> None:
        self.calls = 0
        self.ticks = 0  # advanced by a concurrent coroutine
        self._ticks_seen = -1

    def channels(self) -> tuple[str, ...]:
        return ("x",)

    async def search(self, keyword: str, channel: str, budget_seconds: float) -> SearchAnswer:
        self.calls += 1
        assert self.ticks > self._ticks_seen, "the loop is starved"
        self._ticks_seen = self.ticks
        return SearchAnswer((), 0)
