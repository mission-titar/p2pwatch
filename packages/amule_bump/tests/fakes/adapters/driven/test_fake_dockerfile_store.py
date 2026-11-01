import pytest

from tests.contracts.application.ports.driven.dockerfile_store_contract import (
    DockerfileStoreContract,
)
from tests.fakes.adapters.driven.fake_dockerfile_store import FakeDockerfileStore


class TestFakeDockerfileStore(DockerfileStoreContract):
    @pytest.fixture
    def dockerfile_store(self) -> FakeDockerfileStore:
        return FakeDockerfileStore({})

    @pytest.fixture
    def writer(self, dockerfile_store: FakeDockerfileStore) -> FakeDockerfileStore:
        return dockerfile_store

    @pytest.fixture
    def reader(self, dockerfile_store: FakeDockerfileStore) -> FakeDockerfileStore:
        return dockerfile_store
