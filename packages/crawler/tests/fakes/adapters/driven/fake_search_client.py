from p2pwatch.application.ports.driven.search_client import SearchClient
from p2pwatch.domain.client_errors import ClientUnreachableError, SearchFailedError
from p2pwatch.domain.observation import ReportedFile
from p2pwatch.domain.search.answer import SearchAnswer


class FakeSearchClient(SearchClient):
    """Scripted client (spec §8): ``channels`` are the ones it declares.

    ``results``: list of reported file tuples, one per ``search`` call (exhausted → empty
    tuple). ``search_failures``: exceptions to raise on the first N ``search`` calls (then
    success). Every answer reports ``skipped_result_count`` skipped results.
    """

    def __init__(
        self,
        *,
        channels: tuple[str, ...] = ("ed2k", "kad"),
        results: list[tuple[ReportedFile, ...]] | None = None,
        search_failures: list[Exception] | None = None,
        skipped_result_count: int = 0,
    ) -> None:
        self._channels = channels
        self._results = list(results or [])
        self._skipped_result_count = skipped_result_count
        self._search_failures = list(search_failures or [])
        self.searches: list[tuple[str, str]] = []
        self.budgets: list[float] = []

    def channels(self) -> tuple[str, ...]:
        return self._channels

    async def search(self, keyword: str, channel: str, budget_seconds: float) -> SearchAnswer:
        self.searches.append((keyword, channel))
        self.budgets.append(budget_seconds)
        if self._search_failures:
            raise self._search_failures.pop(0)
        reported_files = self._results.pop(0) if self._results else ()
        return SearchAnswer(reported_files, self._skipped_result_count)


def make_unreachable(message: str = "down") -> ClientUnreachableError:
    return ClientUnreachableError(message)


def make_search_failed(message: str = "search failed") -> SearchFailedError:
    return SearchFailedError(message)
