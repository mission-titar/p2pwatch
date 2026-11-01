import pytest

from tests.contracts.application.ports.driven.tracked_download_store_contract import (
    TrackedDownloadStoreContract,
)
from tests.fakes.adapters.driven.fake_tracked_download_store import FakeTrackedDownloadStore


class TestFakeTrackedDownloadStore(TrackedDownloadStoreContract):
    @pytest.fixture
    def tracked_download_store(self) -> FakeTrackedDownloadStore:
        return FakeTrackedDownloadStore()

    @pytest.fixture
    def writer(self, tracked_download_store: FakeTrackedDownloadStore) -> FakeTrackedDownloadStore:
        return tracked_download_store

    @pytest.fixture
    def reader(self, tracked_download_store: FakeTrackedDownloadStore) -> FakeTrackedDownloadStore:
        return tracked_download_store
