import pytest

from tests.contracts.application.ports.driven.backoff_state_store_contract import (
    BackoffStateStoreContract,
)
from tests.fakes.adapters.driven.fake_backoff_state_store import FakeBackoffStateStore


class TestFakeBackoffStateStore(BackoffStateStoreContract):
    @pytest.fixture
    def backoff_state_store(self) -> FakeBackoffStateStore:
        return FakeBackoffStateStore()
