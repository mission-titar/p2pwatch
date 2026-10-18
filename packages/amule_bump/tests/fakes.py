from typing import Any

from amule_bump.ports.driven.repo_reader import RepoReader


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
