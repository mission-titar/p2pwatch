from p2pwatch.domain.declared_failure import DeclaredFailure
from p2pwatch.domain.health.outcome import Outcome


def test_a_success_carries_no_reason() -> None:
    assert Outcome.success().reason is None


def test_a_declared_outcome_carries_its_failure_as_its_reason() -> None:
    failure = DeclaredFailure("no answer")
    assert Outcome.declared(failure).reason is failure
