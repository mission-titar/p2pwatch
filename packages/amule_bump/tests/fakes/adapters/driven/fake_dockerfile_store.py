from pathlib import PurePath

from amule_bump.application.ports.driven.dockerfile_reader import DockerfileReader
from amule_bump.application.ports.driven.dockerfile_writer import DockerfileWriter


class FakeDockerfileStore(DockerfileReader, DockerfileWriter):
    """Dockerfiles held by path; reading an absent one raises ``FileNotFoundError``."""

    def __init__(self, dockerfile_texts_by_path: dict[PurePath, str]) -> None:
        self.dockerfile_texts_by_path = dockerfile_texts_by_path

    def read_dockerfile(self, dockerfile_path: PurePath) -> str:
        if dockerfile_path not in self.dockerfile_texts_by_path:
            raise FileNotFoundError(f"no Dockerfile at {dockerfile_path}")
        return self.dockerfile_texts_by_path[dockerfile_path]

    def write_dockerfile(self, dockerfile_path: PurePath, dockerfile_text: str) -> None:
        self.dockerfile_texts_by_path[dockerfile_path] = dockerfile_text
