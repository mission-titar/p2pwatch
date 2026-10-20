from pathlib import Path, PurePath

from amule_bump.ports.driven.pull_request_body_writer import PullRequestBodyWriter


class FilesystemPullRequestBodyWriter(PullRequestBodyWriter):
    """The pull request body as a file, which the workflow hands to the action opening the PR."""

    def write_pull_request_body(self, body_path: PurePath, body: str) -> None:
        Path(body_path).write_text(body)
