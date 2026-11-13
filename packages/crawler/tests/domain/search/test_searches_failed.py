from p2pwatch.domain.client_errors import ClientUnreachableError, SearchFailedError
from p2pwatch.domain.health.health_condition import ConditionWindow, Health
from p2pwatch.domain.health.outcome import Outcome
from p2pwatch.domain.search.searches_failed import SEARCHES, SEARCHES_FAILED


def _healths(*outcomes: Outcome) -> list[Health]:
    window, healths = ConditionWindow(condition=SEARCHES_FAILED), []
    for outcome in outcomes:
        window = window.after(outcome)
        healths.append(window.health)
    return healths


def test_the_searches_failed_condition_reads_the_searches_under_both_default_bands() -> None:
    assert SEARCHES_FAILED.source == SEARCHES
    assert [health for health, _ in SEARCHES_FAILED.bands()] == [Health.FAILING, Health.DEGRADED]
    refused = Outcome.declared(SearchFailedError("refused"))
    assert _healths(refused, refused, refused) == [Health.UNKNOWN, Health.UNKNOWN, Health.FAILING]


def test_the_searches_failed_condition_counts_the_refused_searches_alone() -> None:
    unreachable = Outcome.declared(ClientUnreachableError("timeout"))
    assert _healths(unreachable, unreachable, unreachable)[-1] is Health.HEALTHY
