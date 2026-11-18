import pytest

from tests.contracts.application.ports.driven.notification_outbox_store_contract import (
    NotificationOutboxStoreContract,
)
from tests.fakes.adapters.driven.fake_notification_outbox_store import FakeNotificationOutboxStore
from tests.support.refused_writes import RefuseWrites


class TestFakeNotificationOutboxStore(NotificationOutboxStoreContract):
    @pytest.fixture
    def outbox_store(self) -> FakeNotificationOutboxStore:
        return FakeNotificationOutboxStore()

    @pytest.fixture
    def writer(self, outbox_store: FakeNotificationOutboxStore) -> FakeNotificationOutboxStore:
        return outbox_store

    @pytest.fixture
    def reader(self, outbox_store: FakeNotificationOutboxStore) -> FakeNotificationOutboxStore:
        return outbox_store

    @pytest.fixture
    def refuse_writes(self, outbox_store: FakeNotificationOutboxStore) -> RefuseWrites:
        def refuse_writes() -> None:
            outbox_store.writes_fail = True

        return refuse_writes
