import pytest

from tests.contracts.application.ports.driven.tracked_download_store_contract import (
    TrackedDownloadStoreContract,
)
from tests.fakes.adapters.driven.fake_tracked_download_store import FakeTrackedDownloadStore


class TestFakeTrackedDownloadStore(TrackedDownloadStoreContract):
    @pytest.fixture
    def tracked_download_store(self) -> FakeTrackedDownloadStore:
        return FakeTrackedDownloadStore()
