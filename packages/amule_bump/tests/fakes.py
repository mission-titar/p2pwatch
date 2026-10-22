import json
from collections.abc import Mapping
from email.message import Message
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import PurePath
from threading import Thread
from typing import Any, Self
from urllib.request import ProxyHandler, build_opener

from amule_bump.domain.git_object import GitObject
from amule_bump.ports.driven.dockerfile_reader import DockerfileReader
from amule_bump.ports.driven.dockerfile_writer import DockerfileWriter
from amule_bump.ports.driven.pull_request_body_writer import PullRequestBodyWriter
from amule_bump.ports.driven.repo_reader import RepoReader
from amule_bump.ports.driven.step_output_writer import StepOutputWriter


class FakeRepoReader(RepoReader):
    """An upstream repo served from dicts; a file absent from them reads as empty."""

    def __init__(
        self,
        *,
        latest_release_tag: str = "",
        tag_targets_by_tag: dict[str, GitObject] | None = None,
        annotated_tag_targets_by_object_id: dict[str, GitObject] | None = None,
        file_texts_by_ref_and_path: dict[tuple[str, str], str] | None = None,
    ) -> None:
        self._latest_release_tag = latest_release_tag
        self._tag_targets_by_tag = tag_targets_by_tag or {}
        self._annotated_tag_targets_by_object_id = annotated_tag_targets_by_object_id or {}
        self._file_texts_by_ref_and_path = file_texts_by_ref_and_path or {}

    def read_latest_release_tag(self) -> str:
        return self._latest_release_tag

    def read_tag_target(self, tag: str) -> GitObject:
        return self._tag_targets_by_tag[tag]

    def read_annotated_tag_target(self, object_id: str) -> GitObject:
        return self._annotated_tag_targets_by_object_id[object_id]

    def read_file(self, ref: str, path: str) -> str:
        return self._file_texts_by_ref_and_path.get((ref, path), "")


class FakeGitHubServer:
    """GitHub's REST API on a loopback port: set answers by (request path, Accept), 404 otherwise.

    Records each request's path and headers."""

    def __init__(self) -> None:
        self.answers_by_path_and_accept: dict[tuple[str, str], tuple[int, bytes]] = {}
        self.requests: list[tuple[str, Message]] = []
        fake_server = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                fake_server.requests.append((self.path, self.headers))
                accept = self.headers["Accept"]
                status, body = fake_server.answers_by_path_and_accept.get(
                    (self.path, accept), (404, b'{"message": "Not Found"}')
                )
                self.send_response(status)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: Any) -> None:
                """Silent: the requests are recorded instead."""

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        host, port = self._server.server_address[:2]
        self.api_url = f"http://{host!s}:{port}"
        self.url_opener = build_opener(ProxyHandler({}))  # direct, whatever HTTP_PROXY says
        self._thread = Thread(target=self._server.serve_forever)

    def __enter__(self) -> Self:
        self._thread.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._server.shutdown()
        self._thread.join()
        self._server.server_close()

    def answer_json(self, path: str, document: Mapping[str, Any]) -> None:
        self.answers_by_path_and_accept[(path, "application/vnd.github+json")] = (
            200,
            json.dumps(document).encode(),
        )

    def answer_raw(self, path: str, status: int, body: bytes) -> None:
        self.answers_by_path_and_accept[(path, "application/vnd.github.raw+json")] = (status, body)


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
