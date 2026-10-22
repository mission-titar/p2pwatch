from pathlib import Path, PurePath

from amule_bump.application.ports.driven.dockerfile_reader import DockerfileReader
from amule_bump.application.ports.driven.dockerfile_writer import DockerfileWriter


class FilesystemDockerfileStore(DockerfileReader, DockerfileWriter):
    """The Dockerfile as a file at the path each call is given."""

    def read_dockerfile(self, dockerfile_path: PurePath) -> str:
        return Path(dockerfile_path).read_text()

    def set_dockerfile(self, dockerfile_path: PurePath, dockerfile_text: str) -> None:
        Path(dockerfile_path).write_text(dockerfile_text)
