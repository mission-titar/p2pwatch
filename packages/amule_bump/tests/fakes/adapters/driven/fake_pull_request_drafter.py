from pathlib import PurePath

from amule_bump.application.ports.driven.pull_request_drafter import PullRequestDrafter


class FakePullRequestDrafter(PullRequestDrafter):
    """Keeps each body it is given by its path."""

    def __init__(self) -> None:
        self.bodies_by_path: dict[PurePath, str] = {}

    def draft_pull_request_body(self, body_path: PurePath, body: str) -> None:
        self.bodies_by_path[body_path] = body
