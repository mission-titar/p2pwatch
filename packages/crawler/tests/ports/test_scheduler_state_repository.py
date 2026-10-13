import dataclasses

import pytest

from p2pwatch.ports.scheduler_state_repository import (
    BackoffState,
    SchedulerStateRepository,
)


class _StubRepository:
    """Satisfies SchedulerStateRepository structurally (without importing it)."""

    def __init__(self) -> None:
        self.backoff: dict[str, BackoffState] = {}

    def load_backoff_states(self) -> dict[str, BackoffState]:
        return dict(self.backoff)

    def save_backoff_states(self, backoff: dict[str, BackoffState]) -> None:
        self.backoff = dict(backoff)


def test_channel_backoff_is_frozen_and_holds_fields() -> None:
    state = BackoffState(attempts=2, retry_after="2026-06-12T10:05:00.000000+00:00")
    assert state.attempts == 2
    assert state.retry_after == "2026-06-12T10:05:00.000000+00:00"
    with pytest.raises(dataclasses.FrozenInstanceError):
        state.attempts = 3  # type: ignore[misc]


def test_protocol_is_satisfied_structurally() -> None:
    repository: SchedulerStateRepository = _StubRepository()
    assert repository.load_backoff_states() == {}
    state = {
        "amule-1:kad": BackoffState(attempts=1, retry_after="2026-06-12T10:00:00.000000+00:00")
    }
    repository.save_backoff_states(state)
    assert isinstance(repository, _StubRepository)
    assert repository.load_backoff_states() == state
