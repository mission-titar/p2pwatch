from pathlib import Path

import pytest

from amule_bump.adapters.driven.filesystem_dockerfile_store import FilesystemDockerfileStore
from tests.contracts.application.ports.driven.dockerfile_store_contract import (
    DockerfileStoreContract,
)


class TestFilesystemDockerfileStore(DockerfileStoreContract):
    @pytest.fixture
    def dockerfile_store(self) -> FilesystemDockerfileStore:
        return FilesystemDockerfileStore()

    @pytest.fixture
    def writer(self, dockerfile_store: FilesystemDockerfileStore) -> FilesystemDockerfileStore:
        return dockerfile_store

    @pytest.fixture
    def reader(self, dockerfile_store: FilesystemDockerfileStore) -> FilesystemDockerfileStore:
        return dockerfile_store


def test_set_dockerfile_replaces_the_file_s_text(tmp_path: Path) -> None:
    dockerfile_path = tmp_path / "Dockerfile"
    dockerfile_path.write_text("FROM debian\nARG A=1\n")
    FilesystemDockerfileStore().set_dockerfile(dockerfile_path, dockerfile_text="FROM debian\n")
    assert dockerfile_path.read_text() == "FROM debian\n"
