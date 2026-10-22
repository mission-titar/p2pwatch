from pathlib import Path, PurePath

from amule_bump.application.ports.driven.pull_request_drafter import PullRequestDrafter


class FilesystemPullRequestDrafter(PullRequestDrafter):
    """The pull request body as a file, which the workflow hands to the action opening the PR."""

    def draft_pull_request_body(self, body_path: PurePath, body: str) -> None:
        Path(body_path).write_text(body)
