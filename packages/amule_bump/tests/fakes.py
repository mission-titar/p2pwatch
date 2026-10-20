from pathlib import PurePath
from typing import Any

from amule_bump.ports.driven.dockerfile import DockerfileReader, DockerfileWriter
from amule_bump.ports.driven.pull_request_body_writer import PullRequestBodyWriter
from amule_bump.ports.driven.repo_reader import RepoReader
from amule_bump.ports.driven.step_output_writer import StepOutputWriter


class FakeRepoReader(RepoReader):
    """An upstream repo served from dicts: API paths to JSON, and (tag, path) to file text."""

    def __init__(
        self, json: dict[str, Any] | None = None, files: dict[tuple[str, str], str] | None = None
    ) -> None:
        self._json = json or {}
        self._files = files or {}

    def json(self, path: str) -> Any:
        return self._json[path]

    def file(self, ref: str, path: str) -> str:
        return self._files.get((ref, path), "")


class FakeDockerfile(DockerfileReader, DockerfileWriter):
    """Dockerfiles held by path; reading an absent one raises ``FileNotFoundError``."""

    def __init__(self, dockerfile_texts_by_path: dict[PurePath, str]) -> None:
        self.dockerfile_texts_by_path = dockerfile_texts_by_path

    def read_dockerfile(self, dockerfile_path: PurePath) -> str:
        if dockerfile_path not in self.dockerfile_texts_by_path:
            raise FileNotFoundError(f"no Dockerfile at {dockerfile_path}")
        return self.dockerfile_texts_by_path[dockerfile_path]

    def write_dockerfile(self, dockerfile_path: PurePath, dockerfile_text: str) -> None:
        self.dockerfile_texts_by_path[dockerfile_path] = dockerfile_text


class FakePullRequestBodyWriter(PullRequestBodyWriter):
    """Keeps each body it is given by its path."""

    def __init__(self) -> None:
        self.bodies_by_path: dict[PurePath, str] = {}

    def write_pull_request_body(self, body_path: PurePath, body: str) -> None:
        self.bodies_by_path[body_path] = body


class FakeStepOutputWriter(StepOutputWriter):
    """Records each announcement, in order."""

    def __init__(self) -> None:
        self.step_outputs: list[tuple[str, PurePath]] = []

    def write_step_outputs(self, version: str, body_path: PurePath) -> None:
        self.step_outputs.append((version, body_path))
