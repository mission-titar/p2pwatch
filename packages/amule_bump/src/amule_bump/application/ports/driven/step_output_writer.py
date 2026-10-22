from abc import ABC, abstractmethod
from pathlib import PurePath


class BumpAnnouncer(ABC):
    """Hands the workflow's next step what the bump wrote."""

    @abstractmethod
    def announce_bump(self, version: str, body_path: PurePath) -> None:
        """Announces the new pin's version and the path of the pull request body."""
