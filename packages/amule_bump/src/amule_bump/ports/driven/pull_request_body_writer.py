from abc import ABC, abstractmethod
from pathlib import PurePath


class PullRequestBodyWriter(ABC):
    """Writes the bump's pull request body where the workflow reads it."""

    @abstractmethod
    def write_pull_request_body(self, body_path: PurePath, body: str) -> None:
        """Replaces the text at ``body_path`` with ``body``."""
