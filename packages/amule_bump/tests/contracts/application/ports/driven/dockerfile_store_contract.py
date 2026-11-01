"""The promise of the ``DockerfileReader`` and ``DockerfileWriter`` pair."""

from abc import ABC, abstractmethod
from pathlib import Path

import pytest

from amule_bump.application.ports.driven.dockerfile_reader import DockerfileReader
from amule_bump.application.ports.driven.dockerfile_writer import DockerfileWriter


class DockerfileStoreContract(ABC):
    @pytest.fixture
    @abstractmethod
    def writer(self) -> DockerfileWriter:
        """The writer of a store holding no Dockerfile yet."""

    @pytest.fixture
    @abstractmethod
    def reader(self) -> DockerfileReader:
        """The reader of the writer's store."""

    @pytest.fixture
    def dockerfile_path(self, tmp_path: Path) -> Path:
        return tmp_path / "Dockerfile"

    def test_a_dockerfile_never_set_cannot_be_read(
        self, *, reader: DockerfileReader, dockerfile_path: Path
    ) -> None:
        with pytest.raises(OSError):
            reader.read_dockerfile(dockerfile_path)

    def test_a_set_dockerfile_is_read_back(
        self, *, writer: DockerfileWriter, reader: DockerfileReader, dockerfile_path: Path
    ) -> None:
        writer.set_dockerfile(dockerfile_path, dockerfile_text="FROM debian\n")
        assert reader.read_dockerfile(dockerfile_path) == "FROM debian\n"

    def test_a_second_dockerfile_replaces_the_first(
        self, *, writer: DockerfileWriter, reader: DockerfileReader, dockerfile_path: Path
    ) -> None:
        writer.set_dockerfile(dockerfile_path, dockerfile_text="FROM debian\nARG A=1\n")
        writer.set_dockerfile(dockerfile_path, dockerfile_text="FROM debian\n")
        assert reader.read_dockerfile(dockerfile_path) == "FROM debian\n"
