import json
from typing import Any
from urllib.error import HTTPError
from urllib.request import OpenerDirector, Request

from amule_bump.application.ports.driven.upstream_client import UpstreamClient
from amule_bump.domain.git_object import GitObject, GitObjectKind


class GithubUpstreamClient(UpstreamClient):
    """Reads the repository ``full_name`` from GitHub's API at ``api_url``, by ``url_opener``,
    each request failing once unanswered for ``timeout_seconds``."""

    def __init__(
        self,
        api_url: str,
        *,
        full_name: str,
        token: str | None,
        url_opener: OpenerDirector,
        timeout_seconds: float,
    ) -> None:
        self._api_url = api_url
        self._full_name = full_name
        self._token = token
        self._url_opener = url_opener
        self._timeout_seconds = timeout_seconds

    def read_latest_release_tag(self) -> str:
        return str(self._get_json("releases/latest")["tag_name"])

    def read_tag_target(self, tag: str) -> GitObject:
        return _git_object(self._get_json(f"git/ref/tags/{tag}")["object"])

    def read_annotated_tag_target(self, object_id: str) -> GitObject:
        return _git_object(self._get_json(f"git/tags/{object_id}")["object"])

    def read_file(self, ref: str, *, path: str) -> str:
        try:
            content = self._get(
                f"contents/{path}?ref={ref}", accept="application/vnd.github.raw+json"
            )
        except HTTPError as error:
            if error.code == 404:  # absent at that ref: reads as empty, so a diff shows it added
                return ""
            raise
        return content.decode()

    def _get_json(self, path: str) -> Any:
        return json.loads(self._get(path, accept="application/vnd.github+json"))

    def _get(self, path: str, *, accept: str) -> bytes:
        headers = {"Accept": accept, "X-GitHub-Api-Version": "2022-11-28"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        request = Request(f"{self._api_url}/repos/{self._full_name}/{path}", headers=headers)
        with self._url_opener.open(request, timeout=self._timeout_seconds) as response:
            content: bytes = response.read()
        return content


# Spelled out, not GitObjectKind(type): vulture sees no member a lookup by value builds.
_KINDS_BY_GITHUB_TYPE = {
    "commit": GitObjectKind.COMMIT,
    "tag": GitObjectKind.TAG,
    "tree": GitObjectKind.TREE,
    "blob": GitObjectKind.BLOB,
}


def _git_object(github_object: Any) -> GitObject:
    return GitObject(
        kind=_KINDS_BY_GITHUB_TYPE[github_object["type"]], object_id=str(github_object["sha"])
    )
