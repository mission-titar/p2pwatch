from abc import ABC, abstractmethod
from pathlib import PurePath


class PullRequestDrafter(ABC):
    """Writes the bump's pull request body where the workflow reads it."""

    @abstractmethod
    def draft_pull_request_body(self, body_path: PurePath, body: str) -> None:
        """Replaces the text at ``body_path`` with ``body``."""
