"""The promise of the ``BackoffStateReader`` and ``BackoffStateWriter`` pair."""

from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from typing import Protocol

import pytest

from p2pwatch.domain.identifiers import Channel, ClientName
from p2pwatch.domain.search.backoff import BackoffKey, BackoffState

_STARTED_AT = datetime(2026, 6, 12, 10, 0, 0, 123456, tzinfo=UTC)
_BACKOFF = {
    BackoffKey(ClientName("amule-1"), Channel("kad")): BackoffState(
        2, _STARTED_AT, timedelta(seconds=300)
    ),
    BackoffKey(ClientName("amule-1"), None): BackoffState(1, _STARTED_AT, timedelta(seconds=2.75)),
}


class BackoffStateStore(Protocol):
    """Both ports of the pair, which one store implements."""

    def read_backoff_states(self) -> dict[BackoffKey, BackoffState]: ...

    def set_backoff_states(self, backoff_state_by_key: dict[BackoffKey, BackoffState]) -> None: ...


class BackoffStateStoreContract(ABC):
    @pytest.fixture
    @abstractmethod
    def backoff_state_store(self) -> BackoffStateStore:
        """A store holding no backoff state yet."""

    def test_no_backoff_state_is_read_before_the_first_save(
        self, backoff_state_store: BackoffStateStore
    ) -> None:
        assert backoff_state_store.read_backoff_states() == {}

    def test_the_backoff_states_saved_are_read_back(
        self, backoff_state_store: BackoffStateStore
    ) -> None:
        backoff_state_store.set_backoff_states(_BACKOFF)
        assert backoff_state_store.read_backoff_states() == _BACKOFF

    def test_a_save_replaces_every_backoff_state_saved_before(
        self, backoff_state_store: BackoffStateStore
    ) -> None:
        later = {
            BackoffKey(ClientName("amule-1"), None): BackoffState(
                2, _STARTED_AT, timedelta(seconds=4)
            ),
            BackoffKey(ClientName("amule-1"), Channel("ed2k")): BackoffState(
                1, _STARTED_AT, timedelta(seconds=2)
            ),
        }
        backoff_state_store.set_backoff_states(_BACKOFF)
        backoff_state_store.set_backoff_states(later)
        assert backoff_state_store.read_backoff_states() == later

    def test_an_empty_save_replaces_every_backoff_state_saved_before(
        self, backoff_state_store: BackoffStateStore
    ) -> None:
        backoff_state_store.set_backoff_states(_BACKOFF)
        backoff_state_store.set_backoff_states({})
        assert backoff_state_store.read_backoff_states() == {}

    def test_a_backoff_state_is_read_with_its_start_aware_in_utc(
        self, backoff_state_store: BackoffStateStore
    ) -> None:
        backoff_state_store.set_backoff_states(_BACKOFF)
        starts = [state.started_at for state in backoff_state_store.read_backoff_states().values()]
        assert [started_at.utcoffset() for started_at in starts] == [timedelta(0), timedelta(0)]
