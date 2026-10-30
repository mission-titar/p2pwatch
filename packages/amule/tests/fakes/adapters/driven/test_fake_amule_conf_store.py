import pytest

from tests.contracts.application.ports.driven.amule_conf_store_contract import (
    AmuleConfPorts,
    AmuleConfStoreContract,
)
from tests.fakes.adapters.driven.fake_amule_conf_store import FakeAmuleConfStore


class TestFakeAmuleConfStore(AmuleConfStoreContract):
    @pytest.fixture
    def amule_conf_store(self) -> FakeAmuleConfStore:
        return FakeAmuleConfStore([])

    @pytest.fixture
    def unreadable_amule_conf_store(self) -> FakeAmuleConfStore:
        amule_conf_store = FakeAmuleConfStore([])
        amule_conf_store.conf = "[eMule]\nMaxUpload=42\n"
        amule_conf_store.read_error = PermissionError("amule.conf is not readable")
        return amule_conf_store

    @pytest.fixture
    def amule_conf_ports(self, amule_conf_store: FakeAmuleConfStore) -> AmuleConfPorts:
        return AmuleConfPorts(writer=amule_conf_store, reader=amule_conf_store)

    @pytest.fixture
    def unreadable_amule_conf_ports(
        self, unreadable_amule_conf_store: FakeAmuleConfStore
    ) -> AmuleConfPorts:
        return AmuleConfPorts(
            writer=unreadable_amule_conf_store, reader=unreadable_amule_conf_store
        )
