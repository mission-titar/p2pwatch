import dataclasses

import pytest

from p2pwatch.ports.scheduler_state_repository import (
    BackoffKey,
    BackoffState,
    SchedulerStateRepository,
)


class _StubRepository:
    """Satisfies SchedulerStateRepository structurally (without importing it)."""

    def __init__(self) -> None:
        self.backoff: dict[BackoffKey, BackoffState] = {}

    def load_backoff_states(self) -> dict[BackoffKey, BackoffState]:
        return dict(self.backoff)

    def save_backoff_states(self, backoff: dict[BackoffKey, BackoffState]) -> None:
        self.backoff = dict(backoff)


def test_a_backoff_key_names_a_channel_or_the_whole_client() -> None:
    channel_key = BackoffKey(client_name="amule-1", channel="kad")
    assert (channel_key.client_name, channel_key.channel) == ("amule-1", "kad")
    assert BackoffKey("amule-1", None) != channel_key
    assert {channel_key: 1}[BackoffKey("amule-1", "kad")] == 1
    with pytest.raises(dataclasses.FrozenInstanceError):
        channel_key.channel = "ed2k"  # type: ignore[misc]


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
        BackoffKey("amule-1", "kad"): BackoffState(
            attempts=1, retry_after="2026-06-12T10:00:00.000000+00:00"
        )
    }
    repository.save_backoff_states(state)
    assert isinstance(repository, _StubRepository)
    assert repository.load_backoff_states() == state
