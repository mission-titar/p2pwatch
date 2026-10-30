"""The promise of the ``DockerfileReader`` and ``DockerfileWriter`` pair."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

import pytest

from amule_bump.application.ports.driven.dockerfile_reader import DockerfileReader
from amule_bump.application.ports.driven.dockerfile_writer import DockerfileWriter


@dataclass(kw_only=True, frozen=True)
class DockerfilePorts:
    """The pair's two ports, which one store implements."""

    writer: DockerfileWriter
    reader: DockerfileReader


class DockerfileStoreContract(ABC):
    @pytest.fixture
    @abstractmethod
    def dockerfile_ports(self) -> DockerfilePorts:
        """The ports of a store holding no Dockerfile yet."""

    @pytest.fixture
    def dockerfile_path(self, tmp_path: Path) -> Path:
        return tmp_path / "Dockerfile"

    def test_a_dockerfile_never_set_cannot_be_read(
        self, *, dockerfile_ports: DockerfilePorts, dockerfile_path: Path
    ) -> None:
        with pytest.raises(OSError):
            dockerfile_ports.reader.read_dockerfile(dockerfile_path)

    def test_a_set_dockerfile_is_read_back(
        self, *, dockerfile_ports: DockerfilePorts, dockerfile_path: Path
    ) -> None:
        dockerfile_ports.writer.set_dockerfile(dockerfile_path, dockerfile_text="FROM debian\n")
        assert dockerfile_ports.reader.read_dockerfile(dockerfile_path) == "FROM debian\n"

    def test_a_second_dockerfile_replaces_the_first(
        self, *, dockerfile_ports: DockerfilePorts, dockerfile_path: Path
    ) -> None:
        dockerfile_ports.writer.set_dockerfile(
            dockerfile_path, dockerfile_text="FROM debian\nARG A=1\n"
        )
        dockerfile_ports.writer.set_dockerfile(dockerfile_path, dockerfile_text="FROM debian\n")
        assert dockerfile_ports.reader.read_dockerfile(dockerfile_path) == "FROM debian\n"
