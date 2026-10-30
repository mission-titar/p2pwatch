import pytest

from tests.contracts.application.ports.driven.tracked_download_store_contract import (
    TrackedDownloadPorts,
    TrackedDownloadStoreContract,
)
from tests.fakes.adapters.driven.fake_tracked_download_store import FakeTrackedDownloadStore


class TestFakeTrackedDownloadStore(TrackedDownloadStoreContract):
    @pytest.fixture
    def tracked_download_store(self) -> FakeTrackedDownloadStore:
        return FakeTrackedDownloadStore()

    @pytest.fixture
    def tracked_download_ports(
        self, tracked_download_store: FakeTrackedDownloadStore
    ) -> TrackedDownloadPorts:
        return TrackedDownloadPorts(writer=tracked_download_store, reader=tracked_download_store)
