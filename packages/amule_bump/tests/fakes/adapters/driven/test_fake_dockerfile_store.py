import pytest

from tests.contracts.application.ports.driven.dockerfile_store_contract import (
    DockerfilePorts,
    DockerfileStoreContract,
)
from tests.fakes.adapters.driven.fake_dockerfile_store import FakeDockerfileStore


class TestFakeDockerfileStore(DockerfileStoreContract):
    @pytest.fixture
    def dockerfile_store(self) -> FakeDockerfileStore:
        return FakeDockerfileStore({})

    @pytest.fixture
    def dockerfile_ports(self, dockerfile_store: FakeDockerfileStore) -> DockerfilePorts:
        return DockerfilePorts(writer=dockerfile_store, reader=dockerfile_store)
