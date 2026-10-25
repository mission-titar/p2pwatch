"""The promise of the ``DockerfileReader`` and ``DockerfileWriter`` pair."""

from abc import ABC, abstractmethod
from pathlib import Path, PurePath
from typing import Protocol

import pytest


class DockerfileStore(Protocol):
    """Both ports of the pair, which one store implements."""

    def read_dockerfile(self, dockerfile_path: PurePath) -> str: ...

    def set_dockerfile(self, dockerfile_path: PurePath, dockerfile_text: str) -> None: ...


class DockerfileStoreContract(ABC):
    @pytest.fixture
    @abstractmethod
    def dockerfile_store(self) -> DockerfileStore:
        """A store holding no Dockerfile yet."""

    @pytest.fixture
    def dockerfile_path(self, tmp_path: Path) -> Path:
        return tmp_path / "Dockerfile"

    def test_a_dockerfile_never_set_cannot_be_read(
        self, dockerfile_store: DockerfileStore, dockerfile_path: Path
    ) -> None:
        with pytest.raises(OSError):
            dockerfile_store.read_dockerfile(dockerfile_path)

    def test_a_set_dockerfile_is_read_back(
        self, dockerfile_store: DockerfileStore, dockerfile_path: Path
    ) -> None:
        dockerfile_store.set_dockerfile(dockerfile_path, "FROM debian\n")
        assert dockerfile_store.read_dockerfile(dockerfile_path) == "FROM debian\n"

    def test_a_second_dockerfile_replaces_the_first(
        self, dockerfile_store: DockerfileStore, dockerfile_path: Path
    ) -> None:
        dockerfile_store.set_dockerfile(dockerfile_path, "FROM debian\nARG A=1\n")
        dockerfile_store.set_dockerfile(dockerfile_path, "FROM debian\n")
        assert dockerfile_store.read_dockerfile(dockerfile_path) == "FROM debian\n"
