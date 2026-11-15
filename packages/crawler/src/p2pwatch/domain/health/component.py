"""The parts of the node whose health is tracked."""

from dataclasses import dataclass

from p2pwatch.domain.declared_failure import DeclaredFailure
from p2pwatch.domain.health.health_condition import HealthCondition, HealthState
from p2pwatch.domain.identifiers import ClientName


@dataclass(kw_only=True, frozen=True)
class HealthTransition:
    """A change in one part's health, such as the aMule client going from healthy to failing."""

    component: "Component"
    condition: HealthCondition
    previous: HealthState
    current: HealthState


class Component:
    """A part of the node whose health is tracked, such as the aMule client."""

    def __init__(
        self, *, name: str, client_name: ClientName, conditions: tuple[HealthCondition, ...]
    ) -> None:
        self.name = name  # "client amuled", as the log names it
        self.client_name = client_name  # "amuled", as the alerts name it
        self._latest_failed: dict[HealthCondition, tuple[bool, ...]]
        self._latest_failed = dict.fromkeys(conditions, ())
        self._states = dict.fromkeys(conditions, HealthState.UNKNOWN)

    def record_failure(
        self, failure: DeclaredFailure, *, condition: HealthCondition
    ) -> HealthTransition | None:
        """Counts a failed attempt for ``condition``, as working if it failed for another reason;
        returns the change of health it caused, if any."""
        return self._record(isinstance(failure, condition.counts), condition=condition)

    def record_success(self, *, condition: HealthCondition) -> HealthTransition | None:
        """Counts an attempt that worked for ``condition``; returns the change it caused, if any."""
        return self._record(False, condition=condition)

    def _record(self, failed: bool, *, condition: HealthCondition) -> HealthTransition | None:
        latest_failed = (*self._latest_failed[condition], failed)[-condition.attempts_kept :]
        previous = self._states[condition]
        current = condition.state_after(latest_failed, previous=previous)
        self._latest_failed[condition], self._states[condition] = latest_failed, current
        if current is previous:
            return None
        return HealthTransition(
            component=self, condition=condition, previous=previous, current=current
        )
